


###############################################################################
###############################################################################
# Copyright (c) 2025, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################








from time import sleep
from nfc import snep, ContactlessFrontend
from ndef import SmartposterRecord,UriRecord,message_encoder
import logging,struct

from threading import Thread, Event

logger = logging.getLogger(__name__)


class NFCClass(Thread):
	def __init__(self,  GUI=None, path='usb'):
		super(NFCClass, self).__init__()
		self._stop_thread = Event()
		self.Link=None
		self.GUI=GUI
		self.path=path

		self.daemon=True	# using daemon mode so control-C will stop the script and the threads and .join() can timeout and if the main thread crashes, then it will all crash and restart automatically (by systemd).

		logger.info('initialized NFC thread')

		self.start()			# auto start on initialization


	def stop(self):
		logger.info('NFC thread stop requested')
		self._stop_thread.set()

	def stopped_thread(self):
		if self._stop_thread.is_set():
			return True
		else:
			return False

	def stop_broadcast(self):
		if self.GUI is not None:		# if GUI is passed, read Link from there instead.
			self.Link=self.GUI.QRLink

		if (self.Link is None) or self.stopped_thread():		# stop if no link to show or the thread was requested to stop
			logger.info('stopping NFC broadcast')
			return True
		else:								# don't stop yet
			return False



	##############################################################################################
	# these functions are only used by the SNEP way which is not currently used and commented out below
	# because SNEP does not work with newer android phones and does not work with iphone.
	# just keeping them here for reference
	##############################################################################################
	def SendLink(self,llc):
		logger.info('sending NFC data')
		snep_client = snep.SnepClient(llc)
		snep_client.put_records([SmartposterRecord(self.Link,'Distributed Charge')])
		logger.info('NFC data should be sent')

	def connected(self,llc):
		logger.info('connecting to NFC radio')
		Thread(target=self.SendLink, args=(llc,)).start()
		logger.info('should be connected to NFC radio')
		return True

	##############################################################################################




	##############################################################################################
	# ** these functions are specific to card emulation mode and are currently in use **
	# (as opposed to SNEP mode which is currently not in use)
	# don't really understand totally what all these functions do. they were created by taking stuff out of
	# https://github.com/nfcpy/nfcpy/blob/master/examples/tagtool.py
	# there is also an example at https://nfcpy.readthedocs.io/en/latest/topics/get-started.html#emulate-a-card
	# but that seems more theoretical and doesn't do anything practical, so that's why
	# the stuff in tagtool.py needed to be used instead.
	# see also notes in the nfc-test script for more about tagtool.py
	##############################################################################################

	def on_startup(self,target):

		# https://ndeflib.readthedocs.io/en/stable/records/uri.html
		# works with new and old android and iphone (but Zeus does not seem to load even though the NFC data is transmitted to the iphone,
		# but it does work if a regular link is sent such as with `ndeftool uri "http://andyschroder.com"|python3 ./tagtool.py emulate - tt3`).
		self.data=b''.join(message_encoder([UriRecord(self.Link)]))

		# https://ndeflib.readthedocs.io/en/stable/records/smartposter.html
		# works with new and old android. NOT SURE ABOUT IPHONE.
#		self.data=b''.join(message_encoder([SmartposterRecord(self.Link,'Distributed Charge')]))


		###########
		self.size=1024
		###########

		ndef_data_size = len(self.data)
		ndef_area_size = ((ndef_data_size + 15) // 16) * 16
		ndef_area_size = max(ndef_area_size, self.size)
		ndef_data_area = bytearray(self.data) + bytearray(ndef_area_size - ndef_data_size)

		# create attribute data
		attribute_data = bytearray(16)
		attribute_data[0] = 0x10
		attribute_data[1] = 12
		attribute_data[2] = 8

		nmaxb = len(ndef_data_area) // 16

		attribute_data[3:5] = struct.pack(">H", nmaxb)
		attribute_data[5:9] = 4 * [0]
		attribute_data[9] = 0
		attribute_data[10:14] = struct.pack(">I", len(self.data))
		attribute_data[10] = 1
		attribute_data[14:16] = struct.pack(">H", sum(attribute_data[:14]))
		self.tt3_data = attribute_data + ndef_data_area

		idm, pmm, sys = '03FEFFE011223344', '01E0000000FFFF00', '12FC'
		target.sensf_res = bytearray.fromhex('01' + idm + pmm + sys)
		target.brty = "212F"

		logger.info("waiting for an NFC tag reader")

		return target


	def on_card_connect(self, tag):
		logger.info("NFC tag activated")

		def ndef_read(block_number, rb, re):
			#logger.debug("tt3 read block #{0}".format(block_number))
			if block_number < len(self.tt3_data) / 16:
				first, last = block_number * 16, (block_number + 1) * 16
				block_data = self.tt3_data[first:last]
				return block_data

		def ndef_write(block_number, block_data, wb, we):
			#logger.debug("tt3 write block #{0}".format(block_number))
			if block_number < len(self.tt3_data) / 16:
				first, last = block_number * 16, (block_number + 1) * 16
				self.tt3_data[first:last] = block_data
				return True

		tag.add_service(0x0009, ndef_read, ndef_write)
		tag.add_service(0x000B, ndef_read, lambda: False)

		return True


	def on_card_release(self, tag):
		logger.info("NFC tag released")
		return True


	##############################################################################################






	def run(self):
		logger.info('starting NFC thread')
		while not self.stopped_thread():
			try:
				if self.GUI is not None:		# if GUI is passed, read Link from there instead.
					self.Link=self.GUI.QRLink
				if self.Link is not None:
					logger.info('starting NFC broadcast for '+self.Link)
					with ContactlessFrontend(self.path) as clf:

						# this way emulates a card/tag. works with old and new android and iphone.
						clf.connect(card={'on-startup': self.on_startup, 'on-connect': self.on_card_connect, 'on-release': self.on_card_release,},terminate=self.stop_broadcast)

						##############################################################################################
						# this way uses SNEP. it seems more reliable and works at longer distances, but doesn't work with newer android or iphone.
						# UPDATE: seems as though card/tag emulation requires more CPU and the GUI was wasting a lot of CPU time
						# regenerating QR codes that have not changed so fixed that to not regenerate a QR code if it has not
						# changed and reliability and distance seems to have improved a bit and is now comparable to SNEP.
						# only keeping this and the functions it depends on in the code here for reference.
						##############################################################################################

						#clf.connect(llcp={'on-connect': self.connected},terminate=self.stop_broadcast)
						##############################################################################################

					logger.info('stopped NFC broadcast')

				else:
					sleep(.1)

			except OSError as error:
				logger.exception(error)
				break

			except:
				logger.exception('error with NFC, trying again')
				sleep(1.5)

		logger.info('stopped NFC thread')











