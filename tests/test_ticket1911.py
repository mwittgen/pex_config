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

import unittest

import lsst.pex.config as pexConf


class SubConfigDefaultsTest(unittest.TestCase):
    def setUp(self):
        class Configurable:
            class ConfigClass(pexConf.Config):
                v = pexConf.Field(dtype=int, doc="dummy int field for registry configurable", default=0)

            def __init__(self, cfg):
                self.value = cfg.v

        self.registry = pexConf.makeRegistry("registry for Configurable", Configurable.ConfigClass)
        self.registry.register("C1", Configurable)
        self.registry.register("C2", Configurable)

    def testCustomDefaults(self):
        class Config1(pexConf.Config):
            r1 = self.registry.makeField("single-item registry field")
            r2 = self.registry.makeField("single-item registry field", multi=True)

            def setDefaults(self):
                self.r1.name = "C1"
                self.r2.names = ["C2"]

        typemap = {"B": Config1}

        class Config2(pexConf.Config):
            c = pexConf.ConfigField(dtype=Config1, doc="holder for Config1")
            b = pexConf.ConfigChoiceField(typemap=typemap, doc="choice holder for Config1")

        c1 = Config1()
        self.assertEqual(c1.r1.name, "C1")
        self.assertEqual(list(c1.r2.names), ["C2"])
        print(c1.r1.target)
        print(c1.r2.targets)
        c1.validate()
        c2 = Config2()
        self.assertEqual(Config2.c.default, Config1)
        self.assertEqual(c2.c.r1.name, "C1")
        self.assertEqual(list(c2.c.r2.names), ["C2"])
        self.assertEqual(type(c2.b["B"]), Config1)
        c2.b.name = "B"
        self.assertEqual(c2.b.active.r1.name, "C1")
        self.assertEqual(list(c2.b.active.r2.names), ["C2"])
        c2.c = Config1


if __name__ == "__main__":
    unittest.main()
