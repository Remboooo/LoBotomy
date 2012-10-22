# make sure flake8 ignores this file: flake8: noqa

import logging
import random
import socket
from threading import Thread
import time

from lobotomy import config, game, LoBotomyException, protocol, util
from lobotomy.player import Player, PlayerState
from lobotomy.quadtree import QuadTree

class LoBotomyServer:
	"""
	Server for a LoBotomy game.
	"""

	def __init__(self, field_dimensions = config.game.field_dimensions, host = config.host.address, port = config.host.port):
		# create battlefield
		self.width, self.height = field_dimensions
		self.field = QuadTree((0, 0, self.width, self.height))

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
		logging.info('game loop started')
		while not self._shutdown:
			# increment internal turn counter
			self.turn_number += 1

			# FIXME: iterating over ALL the players time and time again must be slow

			# send all alive players a new turn command
			for player in self._in_game:
				player.energy = min(player.energy + config.player.turn_heal, 1.0)
				player.signal_begin(self.turn_number, player.energy)

			# wait the configured amount of time for players to submit commands
			time.sleep(config.game.turn_duration / 1000)

			# send all players the end turn command
			for player in self._in_game:
				player.signal_end()

			# decrement wait counters for dead players
			for player in filter(lambda p: p.state is PlayerState.DEAD, self._players.values()):
				player.dead_turns -= 1

			# execute all requested move actions
			self.execute_moves(player for player in self._in_game if player.move_action is not None)

			# execute all requested fire actions
			self.execute_fires(player for player in self._in_game if player.fire_action is not None)

			# execute all requested scan actions
			self.execute_scans(player for player in self._in_game if player.scan_action is not None)

			# remove all dead players from the battlefield
			for player in filter(lambda p: p.state is PlayerState.DEAD, self._in_game):
				self.field.remove(player)

	def execute_moves(self, players):
		for player in players:
			# unpack required information
			angle, distance = player.move_action
			# calculate new values
			x, y = util.move_wrapped((player.x, player.y), angle, distance, (self.width, self.height))
			# log action and subtract energy cost
			cost = game.move_cost(distance)
			# TODO: truncate location tuples to x decimals
			logging.info('player {} moved from {} to {} (cost: {})'.format(
				player.name,
				(player.x, player.y),
				(x, y),
				cost
			))
			player.energy -= cost
			if player.energy <= 0.0:
				# signal player is dead
				player.signal_death(config.game.dead_turns)
			else:
				# move player on the battlefield
				player.move((x, y))

	def execute_fires(self, players):
		for player in players:
			# unpack required information
			(angle, distance, radius, charge) = player.fire_action
			# TODO: log fire action for player

			# calculate the epicenter of the blast
			epicenter = util.move_wrapped((player.x, player.y), angle, distance, (self.width, self.height))

			# subtract energy cost
			cost = game.fire_cost(distance, radius, charge)
			logging.info('player {} at {} fired at {} (radius: {}, charge: {})'.format(
				player.name,
				(player.x, player.y),
				epicenter,
				radius,
				charge
			))

			# calculate the bounding box for the blast
			bounds = (
				epicenter[0] - radius, epicenter[1] - radius,
				epicenter[0] + radius, epicenter[1] + radius
			)
			# collect all players in the bounding box for the blast
			subjects = set()
			# TODO: change self.field.root.bounds into something less aweful
			for region in util.generate_wrapped_bounds(self.field.root.bounds, bounds):
				subjects = subjects.union(self.field.find_all(region))

			# create a wrapped radius to check distance against
			radius = util.WrappedRadius(epicenter, radius, (self.width, self.height))
			# check if subject in blast radius (bounding box possibly selects too many players)
			for subject in subjects:
				# calculate distance to epicenter for all subjects, signal hit if ... hit
				if (subject.x, subject.y) in radius:
					subject.signal_hit(
						player.name,
						util.angle(radius.distance((subject.x, subject.y))[1], epicenter),
						charge
					)

			player.energy -= cost
			if player.energy <= 0.0:
				# signal player is dead
				player.signal_death(config.game.dead_turns)

	def execute_scans(self, players):
		for player in players:
			(radius,) = player.scan_action
			# TODO: log scan action for player
			logging.info('player {} at {} scanned with radius {}'.format(
				player.name,
				(player.x, player.y),
				radius
			))

			# subtract energy cost
			cost = game.scan_cost(radius)
			player.energy -= cost
			if player.energy <= 0.0:
				# signal player is dead
				player.signal_death(config.game.dead_turns)
			else:
				# calculate the bounding box for the scan
				bounds = (
					player.x - radius, player.y - radius,
					player.x + radius, player.y + radius
				)
				# collect all players in the bounding box for the blast
				subjects = set()
				# TODO: change self.field.root.bounds into something less aweful
				for region in util.generate_wrapped_bounds(self.field.root.bounds, bounds):
					subjects = subjects.union(self.field.find_all(region))

				radius = util.WrappedRadius((player.x, player.y), radius, (self.width, self.height))
				# check if subject in scan radius (bounding box possibly selects too many players)
				for subject in subjects:
					# calculate distance to all subjects, signal detect if within scan
					# TODO: using radius twice runs the expensive operation twice
					(distance, wrapped_location) = radius.distance((subject.x, subject.y))
					if subject is not player and (subject.x, subject.y) in radius:
						player.signal_detect(
								subject.name,
								util.angle((player.x, player.y), wrapped_location),
								util.distance((player.x, player.y), wrapped_location),
								subject.energy
						)

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
			self._in_game.remove(player)

		# remove player from online players
		del self._players[name]
		# TODO: include player host
		logging.info('player %s left', name)

	def request_spawn(self, player):
		if player.dead_turns > 0:
			raise LoBotomyException(104)

		# set player start values
		player.energy = config.player.max_energy
		player.x, player.y = (random.random() * self.width, random.random() * self.height)
		self.field.add(player)

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
