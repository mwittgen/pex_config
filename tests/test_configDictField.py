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
import unittest

import lsst.pex.config as pexConfig


class Config1(pexConfig.Config):
    f = pexConfig.Field("f", float, default=3.0)

    def _collectImports(self):
        # Exists to test that imports of dict values are collected
        self._imports.add("builtins")


class Config2(pexConfig.Config):
    d1 = pexConfig.ConfigDictField("d1", keytype=str, itemtype=Config1, itemCheck=lambda x: x.f > 0)


class Config3(pexConfig.Config):
    field1 = pexConfig.ConfigDictField(keytype=str, itemtype=pexConfig.Config, default={}, doc="doc")


class ConfigDictFieldTest(unittest.TestCase):
    def testConstructor(self):
        try:

            class BadKeytype(pexConfig.Config):
                d = pexConfig.ConfigDictField("...", keytype=list, itemtype=Config1)

        except Exception:
            pass
        else:
            raise SyntaxError("Unsupported keytypes should not be allowed")

        try:

            class BadItemtype(pexConfig.Config):
                d = pexConfig.ConfigDictField("...", keytype=int, itemtype=dict)

        except Exception:
            pass
        else:
            raise SyntaxError("Unsupported itemtypes should not be allowed")

        try:

            class BadItemCheck(pexConfig.Config):
                d = pexConfig.ConfigDictField("...", keytype=str, itemtype=Config1, itemCheck=4)

        except Exception:
            pass
        else:
            raise SyntaxError("Non-callable itemCheck should not be allowed")

        try:

            class BadDictCheck(pexConfig.Config):
                d = pexConfig.DictField("...", keytype=int, itemtype=Config1, dictCheck=4)

        except Exception:
            pass
        else:
            raise SyntaxError("Non-callable dictCheck should not be allowed")

    def testAssignment(self):
        c = Config2()
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "d1", {3: 3})
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "d1", {"a": 0})
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "d1", [1.2, 3, 4])
        c.d1 = None
        c.d1 = {"a": Config1, "b": Config1()}

    def testValidate(self):
        c = Config2()
        self.assertRaises(pexConfig.FieldValidationError, Config2.validate, c)

        c.d1 = {"a": Config1(f=0)}
        self.assertRaises(pexConfig.FieldValidationError, Config2.validate, c)

        c.d1["a"].f = 5
        c.validate()

    def testInPlaceModification(self):
        c = Config2(d1={})
        self.assertRaises(pexConfig.FieldValidationError, c.d1.__setitem__, 1, 0)
        self.assertRaises(pexConfig.FieldValidationError, c.d1.__setitem__, "a", 0)
        c.d1["a"] = Config1(f=4)
        self.assertEqual(c.d1["a"].f, 4)

    def testSave(self):
        c = Config2(d1={"a": Config1(f=4)})
        c.save("configDictTest.py")

        # verify _collectImports is called on all the configDictValues
        stringOutput = c.saveToString()
        self.assertIn("import builtins", stringOutput)

        rt = Config2()
        rt.load("configDictTest.py")

        os.remove("configDictTest.py")
        self.assertEqual(rt.d1["a"].f, c.d1["a"].f)

        c = Config2()
        c.save("emptyConfigDictTest.py")
        rt.load("emptyConfigDictTest.py")
        os.remove("emptyConfigDictTest.py")

        self.assertIsNone(rt.d1)

    def testToDict(self):
        c = Config2(d1={"a": Config1(f=4), "b": Config1})
        dict_ = c.toDict()
        self.assertEqual(dict_, {"d1": {"a": {"f": 4.0}, "b": {"f": 3.0}}})

    def testFreeze(self):
        c = Config2(d1={"a": Config1(f=4), "b": Config1})
        c.freeze()

        self.assertRaises(pexConfig.FieldValidationError, setattr, c.d1["a"], "f", 0)

    def testNoArbitraryAttributes(self):
        c = Config2(d1={})
        self.assertRaises(pexConfig.FieldValidationError, setattr, c.d1, "should", "fail")

    def testEquality(self):
        """Test ConfigDictField.__eq__

        We create two configs, with the keys explicitly added in a different
        order and test their equality.
        """
        keys1 = ["A", "B", "C"]
        keys2 = ["X", "Y", "Z", "a", "b", "c", "d", "e"]

        c1 = Config3()
        c1.field1 = {k: pexConfig.Config() for k in keys1}
        for k in keys2:
            c1.field1[k] = pexConfig.Config()

        c2 = Config3()
        for k in keys2 + keys1:
            c2.field1[k] = pexConfig.Config()

        self.assertTrue(pexConfig.compareConfigs("test", c1, c2))


if __name__ == "__main__":
    unittest.main()
