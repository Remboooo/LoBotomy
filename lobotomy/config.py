# make sure flake8 ignores this file: flake8: noqa
import argparse
import sys

# store network details
class host:
	# network address to bind to
	address = ''
	# port to listen on (1452)
	port = sum(map(ord, 'LoBotomyServer'))
	# delay (in seconds) for spectator streams
	spectator_delay = 60
	# interface and port for spectators
	spectator_port = port+1
	spectator_host = ''
	# is host in debug mode?
	debug = False
	# if host is in debug mode, which client names should under full admin
	# control
	debug_names = ''

# store general game settings
class game:
	# turn length, time in ms the server will wait before executing a turn
	turn_duration = 5000
	# internal battle field size
	field_dimensions = (2.0, 2.0)
	# number of turns a player is kept dead
	dead_turns = 5

# store player settings
class player:
	# maximum and starting energy for players
	max_energy = 1.0
	# amount of energy that is recharged at the end of each turn
	turn_heal = 0.2

def parse_args():
	parser = argparse.ArgumentParser(description='A server for the awesome Lobotomy game')

	parser.add_argument('--debug', '-d', action='store_true', dest='host.debug', default=False, help='Run server in debug mode, pausing the server between turns. Also provides a possibility to start the Python debugger (pdb) to inspect server state.')

	parser.add_argument('--debug_names', dest='host.debug_names', default='', help='If debugging is enabled, this contains a list of names of clients for which the server administrator can fully control which messages are sent and which are not. All other connected clients will be handeled by the server itself.')

	parse_result = parser.parse_args()

	# Convert stuff in parse_result to properties of above classes
	# This may be a bit ugly, but was the shortest/cleanest i could come up
	# with :)
	for k, v in vars(parse_result).items():
		target, var = k.split('.')
		setattr(getattr(sys.modules[__name__], target), var, v)

	# If the admin specifies debug_names, we're in debug mode.
	if host.debug_names:
		host.debug = True
		host.debug_names = host.debug_names.split(',')
