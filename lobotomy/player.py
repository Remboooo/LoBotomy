# make sure flake8 ignores this file: flake8: noqa

import logging
import socket
from threading import Thread

from lobotomy import config, game, LoBotomyException, protocol
from lobotomy.quadtree import Point
from lobotomy.util import enum


# enumerate possible player states
PlayerState = enum('VOID', 'WAITING', 'ACTING', 'DEAD')

class Player(Thread, Point):
	"""
	Class modeling a player, handling messages from and to a client.

	TODO: queue signals, just just before end
	"""

	def __init__(self, server, sock):
		# call the constructor of Thread
		Thread.__init__(self)
		# call the constructor of Point
		Point.__init__(self, None, None)

		# indicate being a daemon thread
		self.daemon = True

		self._server = server
		self._sock = sock
		self._shutdown = False

		self._handlers = {
		'join': self.handle_join,
		'spawn': self.handle_spawn,
		'move': self.handle_move,
		'fire': self.handle_fire,
		'scan': self.handle_scan,
		}

		self.state = PlayerState.VOID

		# actions requested by the client
		self.move_action = None
		self.fire_action = None
		self.scan_action = None

		# game state variables
		self.energy = 0.0
		self.dead_turns = 0

	def run(self):
		try:
			# read lines from the socket
			for line in self._sock.makefile():
				try:
					# split line on whitespace
					parts = line.split()
					# first word is the command
					command = parts[0]
					# remainder are arguments
					arguments = parts[1:]
					# parse arguments into their corresponding values
					arguments = protocol.PARSERS[command](*arguments)
					# remove the command, handles have no such argument
					del arguments['command']

					# reaching this point, arguments have been successfully parsed (not validated)

					# handle command
					self._handlers[command](**arguments)
				except LoBotomyException as e:
					self.send_error(e.errno)
				except KeyError as e:
					self.send_error(301)
				except ValueError as e:
					self.send_error(302)
		except Exception as e:
			if not self._shutdown:
				# error occurred during regular operations
				logging.error('unexpected network error, client will crash: %s', str(e))
				self.shutdown()

	def signal_begin(self, turn_number, energy):
		self.state = PlayerState.ACTING

		# reset action requests
		self.move_action = None
		self.fire_action = None
		self.scan_action = None

		self.send(protocol.begin(turn_number, energy).values())

	def signal_end(self):
		self.state = PlayerState.WAITING
		self.send(protocol.end().values())

	def signal_hit(self, name, angle, charge):
		self.send(protocol.hit(name, angle, charge).values())

	def signal_death(self, turns):
		self.state = PlayerState.DEAD
		self.send(protocol.death(turns).values())

	def signal_detect(self, name, angle, distance, energy):
		self.send(protocol.detect(name, angle, distance, energy).values())

	def handle_join(self, name):
		if self.state is not PlayerState.VOID:
			raise LoBotomyException(202)

		try:
			# attempt to register client with server
			self._server.register(name, self)
			# no exception, we're good (real good!)
			self.name = name
			self.state = PlayerState.DEAD
		except LoBotomyException as e:
			self.send_error(e.errno)

	def handle_spawn(self):
		if self.state is not PlayerState.DEAD:
			raise LoBotomyException(202)

		try:
			self._server.request_spawn(self)
			self.state = PlayerState.WAITING
		except LoBotomyException as e:
			self.send_error(e.errno)

	def handle_move(self, angle, distance):
		# check state
		if self.state is not PlayerState.ACTING:
			raise LoBotomyException(202)

		# check action validity
		if game.move_cost(distance) > config.player.max_energy:
			raise LoBotomyException(101)

		self.move_action = (angle, distance)

	def handle_fire(self, angle, distance, radius, charge):
		# check state
		if self.state is not PlayerState.ACTING:
			raise LoBotomyException(202)

		# check action validity
		if game.fire_cost(distance, radius, charge) > config.player.max_energy:
			raise LoBotomyException(102)

		self.fire_action = (angle, distance, radius, charge)

	def handle_scan(self, radius):
		# check state
		if self.state is not PlayerState.ACTING:
			raise LoBotomyException(202)

		# check action validity
		if game.scan_cost(radius) > config.player.max_energy:
			raise LoBotomyException(103)

		self.scan_action = (radius,)

	def send_error(self, error):
		logging.debug('client caused error %d', error)
		self.send(protocol.error(error, protocol.ERRORS[error]).values())

	def send(self, command):
		# send all data as strings separated by spaces, terminated by a newline
		try:
			self._sock.sendall(bytes(' '.join(map(str, command)) + '\n', 'utf-8'))
		except Exception as e:
			logging.error('unexpected network error, client will crash: %s', str(e))
			self.shutdown()

	def shutdown(self):
		# avoid closing and unregistering twice
		if self._shutdown:
			return

		# indicate a shutdown was requested
		self._shutdown = True

		logging.info('shutting down client')
		# close socket
		try:
			self._sock.shutdown(socket.SHUT_RDWR)
			self._sock.close()
		except:
			# ignore at this point
			pass

		# unregister ourselves from the server if we were registered
		# TODO: find better way of determining this
		if not self.name.startswith('Thread-'):
			self._server.unregister(self.name, self)
