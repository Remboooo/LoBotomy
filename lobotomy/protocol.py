# make sure flake8 ignores this file: flake8: noqa

from collections import OrderedDict

# current protocol version
VERSION = 0

# predefine error codes
# TODO: store error codes in constants
ERRORS = {
	101: 'move impossible, costs more than max energy',
	102: 'fire impossible, costs more than max energy',
	103: 'scan impossible, costs more than max energy',
	104: 'action impossible, you are dead',

	201: 'name taken, choose another one',
	202: 'invalid state for command',

	301: 'unrecognized or unsupported command',
	302: 'invalid command',
}

# store message parsers by their command string
PARSERS = {}

def command(name, *types):
	"""
	Creates a command parser for a named command requiring the provided types
	as arguments.
	"""

	def parser(*arguments):
		try:
			# create a list of the command's name and all the arguments
			# coerced to their respective types
			values = OrderedDict(command = name)
			for (i, (arg_name, arg_type)) in enumerate(types):
				values[arg_name] = arg_type(arguments[i])

			return values
		except ValueError as e:
			raise ValueError('malformed argument', str(e))
		except IndexError as e:
			raise ValueError('invalid number of arguments', len(types), len(arguments))

	# map the handler's name to its parser
	PARSERS[name] = parser

	return parser

# join command, format: join <name>
join = command('join',
	('name', str))

# welcome command, format: welcome <version> <energy> <charge> <turn_duration> <turns_left>
welcome = command('welcome',
	('version', int),
	('energy', float),
	('heal', float),
	('turn_duration', int),
	('turns_left', int)
)

# spawn command, format: spawn
spawn = command('spawn')

# begin command, format: begin <turn_number> <energy>
begin = command('begin',
	('turn_number', int),
	('energy', float)
)

# move command, format: move <angle> <distance>
move = command('move',
	('angle', float),
	('distance', float)
)

# fire command, format: fire <angle> <distance> <radius> <charge>
fire = command('fire',
	('angle', float),
	('distance', float),
	('radius', float),
	('charge', float)
)

# scan command, format: scan <radius>
scan = command('scan',
	('radius', float)
)

# end command, format: end
end = command('end')

# hit command, format: hit <name> <epicenter_angle> <charge>
hit = command('hit',
	('name', str),
	('angle', float),
	('charge', float)
)

# death command, format: death <turns>
death = command('death',
	('turns', int)
)

# detect command, format: detect <name> <angle> <distance> <energy>
detect = command('detect',
	('name', str),
	('angle', float),
	('distance', float),
	('energy', float)
)

# error command, format: error <error_number> <explanation>
error = command('error',
	('errno', int),
	('message', str)
)

def parse_msg(msg):
	"""
	Parser helper function. Provide this with a message directly from the
	socket and it will parse it using the correct function, returning
	a dictionary containing parameters for the given protocol message,
	including the message name
	"""
	chunks = msg.split()
	return PARSERS[chunks[0]](*chunks[1:])

