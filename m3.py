###############################################################################
###############################################################################
#Copyright (c) 2020, Andy Schroder
#See the file README.md for licensing information.
###############################################################################
###############################################################################




################################################################
#prepare to easily decode Tesla Model 3 CAN bus messages
################################################################

import cantools

m3=cantools.database.load_file('model3dbc/Model3CAN.dbc')

def getCANvalue(message,IDname,Signal):
	try:
		return m3.get_message_by_name(IDname).decode(message)[Signal]
	except cantools.database.errors.DecodeError:
#		print('Signal not found in DBC file')
		pass
	except:
		raise


