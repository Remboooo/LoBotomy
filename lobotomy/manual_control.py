# make sure flake8 ignores this file: flake8: noqa
import cmd

from lobotomy import protocol

class ManualControl(cmd.Cmd):
	def __init__(self, server, commands, *args):
		super().__init__(*args)
		self.server = server
		self.commands = commands

	def do_hit(self, line):
		return self.parse_command('hit ' + line)

	def help_hit(self):
		print('Inform a host that he has been hit.')
		print('Arguments:')
		print('name: The host\'s name')
		print('angle: The angle (in radians) from which the projectile came')
		print('charge: The charge that was used')

	def do_death(self, line):
		return self.parse_command('death ' + line)

	def help_death(self):
		print('Inform a host that he has been killed.')
		print('Arguments:')
		print('turns: The number of turns he will stay dead')

	def do_detect(self, line):
		return self.parse_command('detect ' + line)

	def help_detect(self):
		print('Inform a host that he has detected another player in his scan')
		print('Arguments:')
		print('name: The name of the player he detected')
		print('angle: The angle that the target was detected')
		print('distance: How far the target is away')
		print('energy: The amount of energy the target has')


	def do_error(self, line):
		return self.parse_command('error ' + line)

	def help_error(self):
		print('Inform the host there has been an error')
		print('Arguments:')
		print('errno: The error number. Possible error numbers are:')
		for errno, exp in protocol.ERRORS.items():
			print(errno, ':', exp)
		print('message: A message indicating what went wrong')

	def parse_command(self, command):
		try:
			cmd = protocol.parse_msg(command)
			self.commands.append(cmd)
			print('Will send command ' + str(list(str(k) + ' : ' + str(v) for (k,v) in cmd.items())))
		except ValueError as e:
			print('Error while parsing command:')
			print(e)

	def do_continue(self, line):
		return True

	def help_continue(self):
		print('Continue with the commands currently gathered')

	def do_quit(self, line):
		self.server.shutdown()
		return True

	def help_quit(self):
		print('Shut down the server completely')

	def do_EOF(self, line):
		return True
