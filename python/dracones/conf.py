#  Draoones Web-Mapping Framework
#  ==============================
#
#  http://surveillance.mcgill.ca/dracones
#  Copyright (c) 2009, Christian Jauvin
#  All rights reserved. See LICENSE.txt for BSD license notice

"""
Dracones module auto-configuration.
The import of this script does two things:
  1. Read the dracones core config file and import all the specific application config files found in a dict.
  2. Override Pesto Session save method for Pesto < 16
"""

import re
from os import path
from mapscript import *
try:
    import simplejson as json
except ImportError:
    import json


# Core conf.json file is in the Dracones root folder (we are currently in <dracones>/python/dracones/).
conf_filepath = path.join(path.dirname(__file__), '../../conf.json')
dconf = json.load(open(conf_filepath))
"""This dict will contain the core config options, as well as the application specific config options."""

for app_conf_filepath in dconf["app_conf_filepaths"]:
    app_conf = json.load(open(app_conf_filepath))
    assert 'app_name' in app_conf
    dconf[app_conf['app_name']] = app_conf


import pesto

if int(pesto.__version__) < 16:

    from pesto.session.base import Session

    def session_save_override(self):
        """
        Mandatory Pesto Session save method override.

        This is a little hack that intercepts the Pesto WSGI library Sesssion.save() calls
        and make sure that their corresponding Session object will be marked dirty and properly
        saved. The problem with the unmodified code is that mutations performed in this way, for instance:

        C{sess[foo].append(bar)}

        wont be catched. Oliver Cope offered that it would be changed in the next version, but for the
        moment, this works. As of Pesto 16, this is no longer needed.
        """
        for k in self:
            self[k] = self[k]
        self.old_save()

    setattr(Session, 'old_save', Session.save)
    setattr(Session, 'save', session_save_override)
