# This file is part of pex_config.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (http://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This software is dual licensed under the GNU General Public License and also
# under a 3-clause BSD license. Recipients may choose which of these licenses
# to use; please see the files gpl-3.0.txt and/or bsd_license.txt,
# respectively.  If you choose the GPL option then the following text applies
# (but note that there is still no warranty even if you opt for BSD instead):
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Test that we can load a YAML config of a Config class that we have
not previously imported.
"""

import unittest

try:
    import yaml
except ImportError:
    yaml = None

# We have to import the core package to allow the standardized
# yaml constructor to be registered for all subclasses
import lsst.pex.config  # noqa: F401

# The serialized YAML form was created by doing:
# from ticketDM26008helper.unloaded import Unloaded
# c = Unloaded()
# c.c = "World"
# print(yaml.dump(c))

serialized = """
!<lsst.pex.config.Config> |
  import ticketDM26008helper.unloaded
  assert type(config)==ticketDM26008helper.unloaded.Unloaded, 'config is of type %s.%s instead of ticketDM26008helper.unloaded.Unloaded' % (type(config).__module__, type(config).__name__)
  # integer test
  config.i=None

  # float test
  config.f=3.0

  # boolean test
  config.b=False

  # choice test
  config.c='World'

  # Range test
  config.r=3.0

  # list test
  config.ll=[1, 2, 3]

  # dict test
  config.d={'key': 'value'}

  # nan test
  config.n=float('nan')
"""  # noqa: E501


class UnloadedYaml(unittest.TestCase):
    @unittest.skipIf(yaml is None, "pyyaml not available")
    def testLoadUnloaded(self):
        loaded = yaml.safe_load(serialized)
        self.assertEqual(loaded.c, "World")


if __name__ == "__main__":
    unittest.main()
