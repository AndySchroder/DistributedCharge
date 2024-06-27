


###############################################################################
###############################################################################
# Copyright (c) 2022, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################








from helpers2 import TimeStampedPrint
from zmq import SNDMORE


HeaderSize	= 10			#10 should allow 10**10 bytes to be sent.
DataSize	= 1014+HeaderSize


def SendMessage(TheMessage,TheConnection,EchoPrint=True):
	"""Indicate the number of bytes the total message is first and then send the
	message in as many chunks as the client wants them sent in.
	"""
	TheMessageToSend = f"{len(TheMessage):<{HeaderSize}}"+TheMessage
	TheConnection.sendall(TheMessageToSend.encode())
	if EchoPrint:
		TimeStampedPrint('Sent:     '+TheMessage)


def ReceiveMessage(TheSocket):
	"""Receive multiple data chunks and put them together to forma a message.
	HeaderSize indicates the amount of bytes at the beginning that are used
	to define the entire message length.
	"""
	Message = ''
	NewMessage = True
	while True:	#receive data until a complete message is reconstructed
		data = TheSocket.recv(DataSize)
		if data:		#match non-empty message
			if NewMessage:
				MessageLength = int(data[:HeaderSize])
				Message = ""
				NewMessage = False

			Message += data.decode()	#all messages are text right now since they are all json

			if len(Message)-HeaderSize == MessageLength:
				NewMessage = True
				TimeStampedPrint('Received: '+Message[HeaderSize:])
				return Message[HeaderSize:]
		else:
			TimeStampedPrint('Received: '+data.decode())
			return data.decode()	#should be empty.



def PackTopicAndJSONAndSend(ZMQSocket,Topic,JSON):
	#send the topic first
	ZMQSocket.send_string(Topic, flags=SNDMORE)

	#then send the data
	ZMQSocket.send_json(JSON)


def ReceiveAndUnPackTopicAndJSON(socket):

	# with this way of ZMQ receiving, seems like each part of the multi part message is received manually, but after the topic filter was smart enough to know to filter.
	# so, it seems as though the number of parts needs to be known in order to manually receive a multi part message.
	Topic=socket.recv_string()
	JSON=socket.recv_json()

	return Topic,JSON


