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

import os
import pickle
import unittest

import lsst.pex.config as pexConfig


class Config1(pexConfig.Config):
    f = pexConfig.Field(doc="Config1.f", dtype=int, default=4)

    def validate(self):
        pexConfig.Config.validate(self)
        if self.f <= 0:
            raise pexConfig.FieldValidationError(Config1.f, self, "f should be > 0")


class Config2(pexConfig.Config):
    f = pexConfig.Field(doc="Config2.f", dtype=float, default=0.5, check=lambda x: x > 0)


TYPEMAP = {"AAA": Config1, "BBB": Config2, "CCC": Config1}


class Config3(pexConfig.Config):
    a = pexConfig.ConfigChoiceField(
        doc="single non-optional", typemap=TYPEMAP, default="AAA", multi=False, optional=False
    )
    b = pexConfig.ConfigChoiceField(
        doc="single optional", typemap=TYPEMAP, default="AAA", multi=False, optional=True
    )
    c = pexConfig.ConfigChoiceField(
        doc="multi non-optional", typemap=TYPEMAP, default=["AAA"], multi=True, optional=False
    )
    d = pexConfig.ConfigChoiceField(
        doc="multi optional", typemap=TYPEMAP, default=["AAA"], multi=True, optional=True
    )


class ConfigChoiceFieldTest(unittest.TestCase):
    def setUp(self):
        self.config = Config3()

    def tearDown(self):
        del self.config

    def testInit(self):
        self.assertEqual(self.config.a.name, "AAA")
        self.assertEqual(self.config.a.active.f, 4)
        self.assertEqual(self.config.a["AAA"].f, 4)
        self.assertEqual(self.config.a["BBB"].f, 0.5)

    def testSave(self):
        self.config.a["AAA"].f = 1
        self.config.a["BBB"].f = 1.0
        self.config.a = "BBB"
        path = "choiceFieldTest.config"
        self.config.save(path)
        roundtrip = Config3()
        roundtrip.load(path)
        os.remove(path)

        self.assertEqual(self.config.a.name, roundtrip.a.name)
        self.assertEqual(self.config.a["AAA"].f, roundtrip.a["AAA"].f)
        self.assertEqual(self.config.a["BBB"].f, roundtrip.a["BBB"].f)

    def testValidate(self):
        self.config.validate()
        self.config.a = "AAA"
        self.config.a["AAA"].f = 0

        self.assertRaises(pexConfig.FieldValidationError, self.config.validate)

        self.config.a = "BBB"
        self.config.validate()

        self.config.a = None
        self.assertRaises(pexConfig.FieldValidationError, self.config.validate)

    def testFreeze(self):
        self.config.freeze()
        self.assertRaises(pexConfig.FieldValidationError, setattr, self.config.a, "name", "AAA")
        self.assertRaises(pexConfig.FieldValidationError, setattr, self.config.a["AAA"], "f", "1")

        # Create a new unfrozen config
        unfrozenConfig = Config3()

        # Add a new entries to the typemap after the config is frozen and check
        # that it is not in the frozen configs keys
        TYPEMAP["DDD"] = Config1
        self.assertNotIn("DDD", self.config.a.keys())

        # Verify that the entry added to the typemap does show up in the
        # unfrozen config
        self.assertIn("DDD", unfrozenConfig.a.keys())

    def testNoArbitraryAttributes(self):
        self.assertRaises(pexConfig.FieldValidationError, setattr, self.config.a, "should", "fail")

    def testSelectionSet(self):
        # test in place modification
        self.config.c.names.add("BBB")
        self.assertEqual(set(self.config.c.names), set(["AAA", "BBB"]))
        self.config.c.names.remove("AAA")
        self.assertEqual(set(self.config.c.names), set(["BBB"]))
        self.assertRaises(KeyError, self.config.c.names.remove, "AAA")
        self.config.c.names.discard("AAA")

        # test bad assignment
        self.assertRaises(pexConfig.FieldValidationError, setattr, self.config.c, "names", "AAA")
        self.config.c.names = ["AAA"]

    def testNoneValue(self):
        self.config.a = None
        self.assertRaises(pexConfig.FieldValidationError, self.config.validate)
        self.config.a = "AAA"
        self.config.b = None
        self.config.validate()
        self.config.c = None
        self.assertRaises(pexConfig.FieldValidationError, self.config.validate)
        self.config.c = ["AAA"]
        self.config.d = None
        self.config.validate()

    def testNoPickle(self):
        """Test that pickle support is disabled for the proxy container."""
        with self.assertRaises(pexConfig.UnexpectedProxyUsageError):
            pickle.dumps(self.config.c)
        with self.assertRaises(pexConfig.UnexpectedProxyUsageError):
            pickle.dumps(self.config.c.names)


if __name__ == "__main__":
    unittest.main()
