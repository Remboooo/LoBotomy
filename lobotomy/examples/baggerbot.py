#!/usr/bin/env python3
# Make sure flake8 ignores this file: flake8: noqa
import logging
import socket
import random
import math
import sys
import os
import signal
newpath = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, newpath)
import protocol

from pybrain.rl.environments import Environment, EpisodicTask
from pybrain.rl.agents import OptimizationAgent
from pybrain.rl.experiments import EpisodicExperiment
from pybrain.optimization import PGPE
from pybrain.structure.modules.tanhlayer import TanhLayer
from pybrain.tools.shortcuts import buildNetwork

import pickle as pickle
from threading import Condition, Semaphore
from time import time
import numpy as np

SERVER_URL = 'localhost'
SERVER_PORT = 1452
BUF_SIZE = 4096
BOT_NAME = 'HURRDURR'

class BotEnvironment(Environment):
	indim = 7
	outdim = 5

	def __init__(self, connection):
		self.conn = connection
		self.in_game = False
		self.playing = False
		self.energy = 0
		self.max_energy = 0
		self.heal = 0.0
		self.turn_duration = 0
		self.turns_left = 0
		self.turn_number = 0
		self.detected_distance = 0
		self.detected_angle = 0
		self.detected_health = 0
		self.was_hit = False 
		self.hit_angle = 0
		self.hit_charge = 0
		self.error = False

	def getSensors(self):
		#:rtype: by default, this is assumed to be a numpy array of doubles
		r = [self.energy/self.max_energy, self.heal/self.max_energy, self.detected_distance, self.detected_angle, self.detected_health]
		logging.debug('Sensors: energy = %f, heal = %f, detect distance = %f, detect angle = %f, detect health = %f' % (r[0], r[1], r[2], r[3], r[4]))
		return r

	def performAction(self, action):
		#:key action: an action that should be executed in the Environment.
		#:type action: by default, this is assumed to be a numpy array of doubles
		[move_angle, move_distance, fire_angle, fire_distance, fire_radius, fire_charge, scan_radius] = action
		fire = fire_distance > fire_radius and fire_radius > 0
		self.conn.move(move_angle, move_distance)
		if fire:
			self.conn.fire(fire_angle, fire_distance, fire_radius, fire_charge)
		self.conn.scan(scan_radius)

		# reset per-turn optional detection values
		self.detected_distance = 0
		self.detected_angle = 0
		self.detected_health = 0
		self.was_hit = False
		self.hit_angle = 0
		self.hit_charge = 0
		self.error = False

class SurviveTask(EpisodicTask):
	def __init__(self, environment, connection):
		super().__init__(environment)
		self.conn = connection
		self.env = environment
		self.sensor_limits = [
			(0, 1),				# energy/max_energy
			(0, 1),				# heal/max_energy
			(0, self.env.max_energy),	# detected_distance
			(0, 3.14159),			# detected_angle
			(0, self.env.max_energy),	# detected_health
		]
		self.actor_limits = [
			(0, 3.14159),			# move_angle
			(0, self.env.max_energy), 	# move_distance
			(0, 3.14159), 			# fire_angle
			(0, self.env.max_energy), 	# fire_distance
			(0, self.env.max_energy), 	# fire_radius
			(0, self.env.max_energy), 	# fire_charge
			(0, self.env.max_energy),	# scan_radius
		]

	def getReward(self):
		logging.debug('Waiting for turn..')
		self.conn.start_turn()
		if not self.env.playing:
			logging.debug('Reward = -1 (dead)')
			return -1 # we are dead :(
		else:
			score = 2*(self.env.energy/self.env.max_energy)
			if self.env.was_hit:
				score = score - self.env.hit_charge * .5
			if self.env.error:
				score = score - .25
			reward = max(0.0, min(2.0, score))-1.0
			logging.debug('Reward = %f' % reward)
			return reward

	def isFinished(self):
		return not self.env.playing
	

class BaggerBot:
	def __init__(self, host, port, net=None):
		self.conn = ServerConnection(host, port)
		self.env = self.conn.env
		self.conn.join()
		self.task = SurviveTask(self.env, self.conn)
		self.net = buildNetwork(self.env.outdim, 4, self.env.indim, outclass=TanhLayer)
		self.agent = OptimizationAgent(self.net, PGPE())
		self.experiment = EpisodicExperiment(self.task, self.agent)

	def wait_connected(self):
		self.conn.wait_connected()

	def train(self):
		'''
		Infinitely play the game. Figure out the next move(s), parse incoming
		data, discard all that, do stupid stuff and die :)
		'''
		while self.env.in_game:
			# Ask to be spawned
			logging.info('Requesting spawn...')
			self.conn.send_spawn()
			while not self.env.playing:
				self.conn.parse_pregame()
			while self.env.playing:
				self.experiment.doEpisodes(100)



class ServerConnection:
	def __init__(self, host, port):
		# Join a game
		self.env = BotEnvironment(self)
		self.connected_cond = Condition()
		self.turn_sem = Semaphore(0)
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.connect((host, port))
		self.in_buf = self.sock.makefile('rb', BUF_SIZE)
		self.out_buf = self.sock.makefile('wb', BUF_SIZE)

	def wait_connected(self):
		self.connected_cond.acquire()
		while not self.env.in_game:
			self.connected_cond.wait()
		self.connected_cond.release()

	def start_turn(self):
		while not self.turn_sem.acquire(False):
			self.parse_pregame()

	def join(self):
		'''
		Ask to join a game
		'''
		ok = False
		while not ok:
			self.env.name = BOT_NAME + '%06x' % random.randrange((2 ** 8) ** 3)
			self.send_msg('join ' + self.env.name)
			welcome_msg = self.recv_msg()
			parsed = protocol.parse_msg(welcome_msg)
			ok = parsed['command'] is not 'error'
		self.env.energy = parsed['energy']
		self.env.max_energy = parsed['energy']
		self.env.heal = parsed['heal']
		self.env.turn_duration = parsed['turn_duration']
		self.env.turns_left = parsed['turns_left']
		self.connected_cond.acquire()
		self.env.in_game = True
		self.connected_cond.notify_all()
		self.connected_cond.release()

	def send_spawn(self):
		'''
		Send a spawn request to the server
		'''
		self.send_msg('spawn')

	def parse_pregame(self):
		'''
		Parse all the pre-game messages. These include begin, hit and detect.
		See the protocol description for more details
		'''
		try:
			parsed = protocol.parse_msg(self.recv_msg())
			command = parsed['command']

			if command == 'hit':
				logging.info('We were hit by {0} (angle: {1}, charge: {2})'.format(
					parsed['name'], parsed['angle'], parsed['charge']))
				self.env.was_hit = True
				self.env.hit_angle = parse['angle']
				self.env.hit_charge = parse['charge']
			elif command == 'detect':
				if not self.env.detected_distance or self.env.detected_distance > parsed['distance']:
					self.env.detected_distance = parsed['distance']
					self.env.detected_energy = parsed['energy']
					self.env.detected_angle = parsed['angle']
				logging.info('We detected {0}({1} energy) at (angle: {2}, distance: {3})'.format(
				parsed['name'], parsed['energy'], parsed['angle'], parsed['distance']))
			elif command == 'begin':
				self.env.turn_number = parsed['turn_number']
				self.env.energy = parsed['energy']
				self.env.playing = True
				self.turn_sem.release()
			elif command == 'death':
				self.env.playing = False
			elif command == 'error':
				self.env.error = True
				return
		except KeyError:
		# garbage received
			logging.exception('Pregame message parsing error:')

	def parse_end(self):
		'''
		Parse the end-turn message
		'''
		protocol.parse_msg(self.recv_msg())

	def recv_msg(self):
		'''
		Utility function to retrieve a message
		'''
		line = self.in_buf.readline().decode('utf-8').strip()
		logging.debug('-> %s' % line)
		return line

	def send_msg(self, msg):
		'''
		Utility function to send a message
		'''
		if type(msg) == type([]):
			msg = ' '.join(msg)
		logging.debug('<- %s' % msg)
		self.out_buf.write(bytes(msg if msg.endswith('\n') else msg + '\n',
			'utf-8'))
		self.out_buf.flush()

	def move(self, move_angle, move_distance):
		cmd = 'move '
		cmd += str(move_angle) + ' ' # angle
		cmd += str(move_distance) # distance
		self.send_msg(cmd)

	def fire(self, fire_angle, fire_distance, fire_radius, fire_charge):
		cmd = 'fire '
		cmd += str(fire_angle) + ' ' # angle
		cmd += str(fire_distance) + ' ' # distance
		cmd += str(fire_radius) + ' ' # radius
		cmd += str(fire_charge) # charge
		self.send_msg(cmd)

	def scan(self, scan_radius):
		cmd = 'scan '
		cmd += str(scan_radius) # radius
		self.send_msg(cmd)

def main():
	logging.getLogger().setLevel(logging.DEBUG)
	logging.basicConfig(format='%(asctime)s [ %(levelname)7s ] : %(message)s', level=logging.DEBUG)
	logging.info('HERP DERP')
	bot = BaggerBot(SERVER_URL, SERVER_PORT)
	def signal_handler(signal, frame):
		pickle.dump(bot.net, open('baggerbot%d.brain' % time(), 'wb'))
		sys.exit(0)
	#signal.signal(signal.SIGINT, signal_handler)
	bot.wait_connected()
	bot.train()

if __name__ == '__main__':
	main()
