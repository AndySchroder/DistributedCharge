###############################################################################
###############################################################################
#Copyright (c) 2024, Andy Schroder
#See the file README.md for licensing information.
###############################################################################
###############################################################################




################################################################
#prepare to easily decode Tesla Model 3 CAN bus messages
################################################################

from cantools import database
from pathlib import Path

m3=database.load_file(str(Path(__file__).parent.resolve())+'/model3dbc/Model3CAN.dbc')

def getCANvalue(message,IDname,Signal):
	try:
		return m3.get_message_by_name(IDname).decode(message)[Signal]
	except database.errors.DecodeError:
#		print('Signal not found in DBC file')
		pass
	except:
		raise


