# make sure flake8 ignores this file: flake8: noqa

import logging
import random
import socket
from threading import Thread
import time

from lobotomy import config, game, LoBotomyException, protocol, util
from lobotomy.event import Emitter
from lobotomy.player import Player, PlayerState

class LoBotomyServer(Emitter):
	"""
	Server for a LoBotomy game.
	"""

	def __init__(self, field_dimensions = config.game.field_dimensions, host = config.host.address, port = config.host.port):
		super().__init__()
		# create battlefield
		self.width, self.height = field_dimensions

		self.host = host
		self.port = port

		# track online players by name
		self._players = {}
		# track players in game
		self._in_game = []

		self.turn_number = 0

	def serve_forever(self):
		logging.debug('preparing network setup for serving at "%s:%d"', self.host, self.port)
		self._ssock = socket.socket()
		try:
			# bind a socket to the specified host and port
			self._ssock.bind((self.host, self.port))
			# make the socket listen for new connections
			self._ssock.listen(5)
			logging.info('successfully bound to %s:%d, listening for clients', self.host, self.port)

			self._shutdown = False

			# start a game
			Thread(name = 'game loop', target = self.run_game).start()

			# loop as long as a shutdown was not requested
			while not self._shutdown:
				try:
					# accept a connection from a client
					client, address = self._ssock.accept()
					logging.info('client from %s connected', address[0])
					Player(self, client).start()
				except Exception as e:
					if not self._shutdown:
						# not an expected exception
						logging.critical('unexpected network error, shutting down server: %s', str(e))
		except Exception as e:
			logging.critical('unexpected error: %s', str(e))

		# TODO: close all client threads (not all present in self._players)

	def run_game(self):
		logging.info('main game loop started')
		while not self._shutdown:
			# increment internal turn counter
			self.turn_number += 1

			# FIXME: iterating over ALL the players time and time again must be slow

			# send all alive players a new turn command
			logging.info('turn {}, currently {} players in game'.format(self.turn_number, len(self._in_game)))
			for player in self._in_game:
				if player.state is not PlayerState.DEAD:
					prev_energy = player.energy
					player.energy = min(player.energy + config.player.turn_heal, 1.0)
					# emit heal event with energy mutation
					self.emit_event(
						type = 'player_heal',
						player = player.name,
						energy = (prev_energy, player.energy)
					)
				player.signal_begin(self.turn_number, player.energy)

			# emit turn start event
			self.emit_event(type = 'turn_start', turn = self.turn_number, num_players = len(self._in_game))

			# wait the configured amount of time for players to submit commands
			time.sleep(config.game.turn_duration / 1000)

			# send all players the end turn command
			for player in self._in_game:
				player.signal_end()

			# emit turn end event
			self.emit_event(type = 'turn_end', turn = self.turn_number)

			# decrement wait counters for dead players
			for player in [p for p in self._players.values() if p.state is PlayerState.DEAD]:
				player.dead_turns -= 1
				self.emit_event(
					type = 'player_dead_turns_decrement',
					player = player.name,
					turns = player.dead_turns
				)

			# execute all requested move actions
			self.execute_moves(player for player in self._in_game if player.move_action is not None)

			# execute all requested fire actions
			self.execute_fires(player for player in self._in_game if player.fire_action is not None)

			# execute all requested scan actions
			self.execute_scans(player for player in self._in_game if player.scan_action is not None)

	def find_players(self, bounds):
		"""
		TODO: document me
		"""
		def in_bounds(player):
			p_x, p_y = player.location
			x1, y1, x2, y2 = bounds
			return p_x is not None and x1 <= p_x < x2 and y1 <= p_y < y2

		return set(player for player in self._in_game if in_bounds(player))

	def execute_moves(self, players):
		for player in players:
			# unpack required information
			angle, distance = player.move_action
			# calculate new values
			x, y = util.move_wrapped(player.location, angle, distance, (self.width, self.height))
			# log action and subtract energy cost
			cost = game.move_cost(distance)
			# TODO: truncate location tuples to x decimals
			logging.info('player {} moved from {} to {} (cost: {})'.format(
				player.name,
				player.location,
				(x, y),
				cost
			))
			prev_energy = player.energy
			player.energy -= cost
			self.emit_event(
				type = 'player_move',
				player = player.name,
				angle = angle,
				distance = distance,
				location = (player.location, (x, y)),
				cost = cost,
				energy = (prev_energy, player.energy)
			)
			if player.energy <= 0.0:
				# signal player is dead
				self.player_death(player)
				self.emit_event(
					type = 'player_suicide',
					player = player.name,
					action = 'move',
					cost = cost,
					energy = (prev_energy, player.energy)
				)
				logging.info('player {} died from exhaustion (move)'.format(player.name))
			else:
				# move player on the battlefield
				player.location = (x, y)

	def execute_fires(self, players):
		for player in players:
			# unpack required information
			(angle, distance, radius, charge) = player.fire_action
			# TODO: log fire action for player

			# calculate the epicenter of the blast
			epicenter = util.move_wrapped(player.location, angle, distance, (self.width, self.height))

			# subtract energy cost
			cost = game.fire_cost(distance, radius, charge)
			logging.info('player {} at {} fired at {} (radius: {}, charge: {})'.format(
				player.name,
				player.location,
				epicenter,
				radius,
				charge
			))

			prev_energy = player.energy
			player.energy -= cost

			# emit player fire event
			self.emit_event(
				type = 'player_fire',
				player = player.name,
				location = player.location,
				angle = angle,
				distance = distance,
				radius = radius,
				charge = charge,
				cost = cost,
				epicenter = epicenter,
				energy = (prev_energy, player.energy)
			)

			if player.energy <= 0.0:
				# signal player is dead
				self.player_death(player)
				self.emit_event(
					type = 'player_suicide',
					action = 'fire',
					cost = cost,
					energy = (prev_energy, player.energy)
				)
				# XXX: possibly more to do with hitting one's self
				logging.info('player {} died from exhaustion (fire)'.format(player.name))

			# calculate the bounding box for the blast
			bounds = (
				epicenter[0] - radius, epicenter[1] - radius,
				epicenter[0] + radius, epicenter[1] + radius
			)
			# collect all players in the bounding box for the blast
			subjects = set()
			for region in util.generate_wrapped_bounds((0, 0, self.width, self.height), bounds):
				subjects = subjects.union(self.find_players(region))

			# create a wrapped radius to check distance against
			radius = util.WrappedRadius(epicenter, radius, (self.width, self.height))
			# check if subject in blast radius (bounding box possibly selects too many players)
			for subject in subjects:
				# calculate distance to epicenter for all subjects, signal hit if ... hit
				if subject.location in radius:
					# subtract energy equal to charge from subject that was hit
					prev_energy = subject.energy
					subject.energy -= charge
					# emit player hit event
					self.emit_event(
						type = 'player_hit',
						player = subject.name,
						location = subject.location,
						epicenter = epicenter,
						radius = radius,
						charge = charge,
						energy = (prev_energy, subject.energy),
						fatal = subject.energy <= 0.0,
						attacker = player.name,
						attacker_location = player.location,
						attacker_energy = player.energy
					)
					# signal the subject it was hit
					subject.signal_hit(
						player.name,
						util.angle(radius.distance(subject.location)[1], epicenter),
						charge
					)
					logging.info('player {} hit {} for {} (new energy: {})'.format(player.name, subject.name, charge, subject.energy))
					# check to see if the subject died from this hit
					if subject.energy <= 0.0:
						logging.info("player {} died from {}'s bomb".format(subject.name, player.name))
						self.player_death(subject)

	def execute_scans(self, players):
		for player in players:
			(radius,) = player.scan_action
			logging.info('player {} at {} scanned with radius {}'.format(
				player.name,
				player.location,
				radius
			))

			# subtract energy cost
			cost = game.scan_cost(radius)
			prev_energy = player.energy
			player.energy -= cost

			self.emit_event(
				type = 'player_scan',
				player = player.name,
				location = player.location,
				radius = radius,
				cost = cost,
				energy = (prev_energy, player.energy)
			)
			if player.energy <= 0.0:
				# signal player is dead
				self.player_death(player)
				self.emit_event(
					type = 'player_suicide',
					action = 'scan',
					cost = cost,
					energy = (prev_energy, player.energy)
				)
				logging.info('player {} died from exhaustion (scan)'.format(player.name))
			else:
				x, y = player.location
				# calculate the bounding box for the scan
				bounds = (
					x - radius, y - radius,
					x + radius, y + radius
				)
				# collect all players in the bounding box for the blast
				subjects = set()
				for region in util.generate_wrapped_bounds((0, 0, self.width, self.height), bounds):
					subjects = subjects.union(self.find_players(region))

				radius = util.WrappedRadius(player.location, radius, (self.width, self.height))
				# check if subject in scan radius (bounding box possibly selects too many players)
				for subject in subjects:
					# calculate distance to all subjects, signal detect if within scan
					# TODO: using radius twice runs the expensive operation twice
					(distance, wrapped_location) = radius.distance(subject.location)
					if subject is not player and subject.location in radius:
						player.signal_detect(
								subject.name,
								util.angle(player.location, wrapped_location),
								util.distance(player.location, wrapped_location),
								subject.energy
						)
						self.emit_event(
							type = 'player_detect',
							player = player.name,
							energy = player.energy,
							location = player.location,
							radius = radius,
							detected = subject.name,
							detected_location = subject.location,
							detected_energy = subject.energy
						)
						logging.info('player {} detected {}'.format(player.name, subject.name))

	def player_death(self, player):
		"""
		TODO: document me
		"""
		player.energy = 0.0
		player.location = (None, None)
		# signal death to player
		player.signal_death(config.game.dead_turns)

	def register(self, name, player):
		if name in self._players:
			# TODO: include player host
			logging.debug('player tried to register as %s, name is in use', name)
			raise LoBotomyException(201)

		# register player
		self._players[name] = player
		# send welcome message
		player.send(protocol.welcome(
			protocol.VERSION,
			config.player.max_energy,
			config.player.turn_heal,
			config.game.turn_duration,
			-1
		).values())
		# TODO: include player host
		logging.info('player %s joined', name)

	def unregister(self, name, player):
		# remove player from game if the player is in it
		if player in self._in_game:
			# remove player from game
			self._in_game.remove(player)
			self.emit_event(
				type = 'player_leave',
				player = player.name
			)

		# remove player from online players
		del self._players[name]
		# TODO: include player host
		logging.info('player %s left', name)

	def request_spawn(self, player):
		if player.dead_turns > 0:
			raise LoBotomyException(104)

		# TODO: only spawn player just before turn begin
		# set player start values
		player.energy = config.player.max_energy
		player.location = (random.random() * self.width, random.random() * self.height)

		self.emit_event(
			type = 'player_spawn',
			player = player.name,
			energy = player.energy,
			location = player.location
		)

		# check to see if this is a spawn or a respawn
		if player not in self._in_game:
			self._in_game.append(player)

	def shutdown(self):
		# avoid double shutdown
		if self._shutdown:
			return

		# request shutdown in main loop
		self._shutdown = True
		logging.info('shutting down server')
		# close the socket real good
		try:
			self._ssock.shutdown(socket.SHUT_RDWR)
			self._ssock.close()
		except:
			# ignore at this point
			pass

