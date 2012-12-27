import logging
from lobotomy.event import Emitter, Listener
from threading import Thread, Lock
from time import time, sleep
from collections import deque

class SpectatorEmitter(Emitter, Listener):
	"""
	Emitter that can be observed by spectator-like listeners, applying  a time delay to prevent cheating.
	Server state is saved along with each event, such that spectators may join at any time.
	This state is appended to every emitted event, in the 'server_state' property of the event, as well as a timestamp.
	"""

	def __init__(self, server, delay = 60):
		super().__init__()
		self.delay = delay
		self.server = server
		self.eventqueue = deque()
		self._queuelock = Lock()
		# keep track of last emitted state to send to new spectators
		server.add_listener(self)
		self._last_event = None
		t = Thread(name = 'spectator event pipe', target = self.consumer)
		t.daemon = True
		t.start()

	def accept(self, **event):
		self._queuelock.acquire()
		event['timestamp'] = time()
		state = self.server.get_state()
		event['server_state'] = state
		self.eventqueue.append(event)
		self._queuelock.release()

	def start_spectating(self, listener, state_callback):
		"""
		Same as add_listener, but also provides the listener with the last  
		server state such that spectators know what's up.
		To avoid race conditions, state is returned via a callback
		which has the server state as the sole argument.
		This avoids receiving an event before initial server state is
		processed.
		Do mind that state_callback will block the whole emitter thread...
		state_callback is _NOT_ called when the server has not emitted any events yet.
		"""
		self._queuelock.acquire()
		if self._last_event:
			state_callback(self._last_event['server_state'])
		self.add_listener(listener)
		self._queuelock.release()

	def consumer(self):
		while not self.server._shutdown:
			self._queuelock.acquire()
			wait = 0
			now = time()
			if self.eventqueue:
				event = self.eventqueue[0]
				wait = (event['timestamp'] + self.delay) - now
				if wait <= 0:
					self._last_event = event
					self.emit_event(**event)
					self.eventqueue.popleft()
			else:
				wait = self.delay

			self._queuelock.release()
			if wait > 0:
				sleep(wait)
