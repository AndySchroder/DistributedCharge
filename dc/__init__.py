


###############################################################################
###############################################################################
# Copyright (c) 2024, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################







from pathlib import Path





# this initialization module is intentionally very small. its purpose is to
# be abe to set global variables that can be used by all modules


# `mode` needs to be reset to something meaningful by the most top level
# parent script that first imports this module after importing it,
# but before importing any other modules

mode=None		#options are 'car', 'wall', 'grid-buyer', 'grid-seller'

LNDhost=None

# the default value of `TheConfigFile` can be overridden, but if not, this
# default value will be used
TheConfigFile='Config.yaml'
TheDataFolder=str(Path.home())+'/.dc/'
