# simple event emitter module

class Listener:
	def __init__(self):
		pass

	def accepts(self, **event):
		return True

	def submit(self, **event):
		if self.accepts(**event):
			self.accept(**event)

	def accept(self, **event):
		# to be overridden by implementors
		pass

class Emitter:
	def __init__(self):
		self._listeners = []

	def add_listener(self, listener):
		self._listeners.append(listener)

	def remove_listener(self, listener):
		try:
			self._listeners.remove(listener)
		except ValueError:
			pass

	def emit_event(self, **kwargs):
		for sink in self._listeners:
			sink.submit(**kwargs)

