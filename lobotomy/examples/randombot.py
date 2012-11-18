#!/usr/bin/env python3
# Make sure flake8 ignores this file: flake8: noqa
import logging
import socket
import random
import math
import sys
import os
newpath = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, newpath)
import protocol

SERVER_URL = 'localhost'
SERVER_PORT = 1452
BUF_SIZE = 4096
BOT_NAME = 'Henk_' + str(random.randint(0, 2**16))


class ExampleBot:
	def __init__(self, host, port):
		# Join a game
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.connect((host, port))
		self.in_buf = self.sock.makefile('rb', BUF_SIZE)
		self.out_buf = self.sock.makefile('wb', BUF_SIZE)
		self.in_game = False
		self.playing = False
		self.energy = 0
		self.max_energy = 0
		self.heal = 0.0
		self.turn_duration = 0
		self.turns_left = 0
		self.turn_number = 0


	def play(self):
		'''
		Infinitely play the game. Figure out the next move(s), parse incoming
		data, try to win :)
		'''
		self.send_join()
		# Receive welcome message
		self.parse_welcome()

		while self.in_game:
			# Ask to be spawned
			self.send_spawn()
			self.parse_pregame()
			while self.playing:
				logging.info('Let\'s play! (at {} energy)'.format(self.energy))
				# Wait for begin
				cmds = self.determine_commands()
				for cmd in cmds:
					self.send_msg(cmd)
				self.parse_end()
				self.parse_pregame()

	def send_join(self):
		'''
		Ask to join a game
		'''
		self.send_msg('join ' + BOT_NAME)

	def parse_welcome(self):
		'''
		Receive the welcome message, parse all info in it and start playing
		'''
		welcome_msg = self.recv_msg()
		parsed = protocol.parse_msg(welcome_msg)
		self.energy = parsed['energy']
		self.max_energy = parsed['energy']
		self.heal = parsed['heal']
		self.turn_duration = parsed['turn_duration']
		self.turns_left = parsed['turns_left']
		self.in_game = True

	def send_spawn(self):
		'''
		Send a spawn request to the server
		'''
		logging.info('Requesting spawn...')
		self.send_msg('spawn')

	def parse_pregame(self):
		'''
		Parse all the pre-game messages. These include begin, hit and detect.
		See the protocol description for more details
		'''
		while True:
			try:
				parsed = protocol.parse_msg(self.recv_msg())
				command = parsed['command']

				if command == 'hit':
					logging.info('We were hit by {0} (angle: {1}, charge: {2})'.format(
						parsed['name'], parsed['angle'], parsed['charge']))
				elif command == 'detect':
					logging.info('We detected {0}({1} energy) at (angle: {2}, distance: {3})'.format(
						parsed['name'], parsed['energy'], parsed['angle'], parsed['distance']))
				elif command == 'begin':
					self.turn_number = parsed['turn_number']
					self.energy = parsed['energy']
					self.playing = self.energy > 0.0
					return
				elif command == 'death':
					logging.info('We died! Dead for {} turns'.format(parsed['turns']))
					self.playing = False
				else:
					continue
			except KeyError:
			# garbage received
				logging.exception('Pregame message parsing error:')
				continue

	def parse_end(self):
		'''
		Parse the end-turn message
		'''
		protocol.parse_msg(self.recv_msg())

	def determine_commands(self):
		'''
		The heart of the AI of the robot. If you implement anything, implement
		this, and please don't just let it drive around for half an hour, then
		blow itself up.
		'''
		energy_remaining = self.energy
		cmds = []
		# Think of move
		if random.randint(0, 1):
			cmd = 'move '
			cmd += str(random.random() * 2 * math.pi) + ' ' # angle
			cmd += str(random.random() * 0.4 * self.energy) # distance
			cmds.append(cmd)
		# Think of fire
		if random.randint(0, 1):
			cmd = 'fire '
			cmd += str(random.random() * 2 * math.pi) + ' ' # angle
			cmd += str(random.random() * 0.2 * self.energy) + ' ' # distance
			cmd += str(random.random() * 0.2 * self.energy) + ' ' # radius
			cmd += str(random.random() * 0.4 * self.energy) # charge
			cmds.append(cmd)
		# Think of scan
		if random.randint(0, 1):
			cmd = 'scan '
			cmd += str(random.random() * 0.4 * self.energy) # radius
			cmds.append(cmd)
		return cmds

	def recv_msg(self):
		'''
		Utility function to retrieve a message
		'''
		line = self.in_buf.readline().decode('utf-8').strip()
		return line

	def send_msg(self, msg):
		'''
		Utility function to send a message
		'''
		if type(msg) == type([]):
			msg = ' '.join(msg)
		self.out_buf.write(bytes(msg if msg.endswith('\n') else msg + '\n',
			'utf-8'))
		self.out_buf.flush()



def main():
	logging.basicConfig(format='%(asctime)s [ %(levelname)7s ] : %(message)s',
			level=logging.INFO)

	bot = ExampleBot(SERVER_URL, SERVER_PORT)
	bot.play()

if __name__ == '__main__':
	main()
