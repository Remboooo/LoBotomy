from threading import Thread
import baggerbot

def main():
	for i in range(100):
		Thread(target=baggerbot.main).start()

if __name__ == '__main__':
	main()
