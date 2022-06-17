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

import pickle
import unittest

import lsst.pex.config as pexConfig


class Config1(pexConfig.Config):
    d1 = pexConfig.DictField("d1", keytype=str, itemtype=int, default={"hi": 4}, itemCheck=lambda x: x > 0)
    d2 = pexConfig.DictField("d2", keytype=str, itemtype=str, default=None)
    d3 = pexConfig.DictField("d3", keytype=float, itemtype=float, optional=True, itemCheck=lambda x: x > 0)
    d4 = pexConfig.DictField("d4", keytype=str, itemtype=None, default={})


class DictFieldTest(unittest.TestCase):
    def testConstructor(self):
        try:

            class BadKeytype(pexConfig.Config):
                d = pexConfig.DictField("...", keytype=list, itemtype=int)

        except Exception:
            pass
        else:
            raise SyntaxError("Unsupported keyptype DictFields should not be allowed")

        try:

            class BadItemtype(pexConfig.Config):
                d = pexConfig.DictField("...", keytype=int, itemtype=dict)

        except Exception:
            pass
        else:
            raise SyntaxError("Unsupported itemtype DictFields should not be allowed")

        try:

            class BadItemCheck(pexConfig.Config):
                d = pexConfig.DictField("...", keytype=int, itemtype=int, itemCheck=4)

        except Exception:
            pass
        else:
            raise SyntaxError("Non-callable itemCheck DictFields should not be allowed")

        try:

            class BadDictCheck(pexConfig.Config):
                d = pexConfig.DictField("...", keytype=int, itemtype=int, dictCheck=4)

        except Exception:
            pass
        else:
            raise SyntaxError("Non-callable dictCheck DictFields should not be allowed")

    def testFieldTypeAnnotationRuntime(self):
        # test parsing type annotation for runtime keytype, itemtype
        testField = pexConfig.DictField[str, int](doc="")
        self.assertEqual(testField.keytype, str)
        self.assertEqual(testField.itemtype, int)

        # verify that forward references work correctly
        testField = pexConfig.DictField["float", "int"](doc="")
        self.assertEqual(testField.keytype, float)
        self.assertEqual(testField.itemtype, int)

        # verify that Field rejects single types
        with self.assertRaises(ValueError):
            pexConfig.DictField[int](doc="")  # type: ignore

        # verify that Field raises in conflict with keytype, itemtype
        with self.assertRaises(ValueError):
            pexConfig.DictField[str, int](doc="", keytype=int)

        with self.assertRaises(ValueError):
            pexConfig.DictField[str, int](doc="", itemtype=str)

        # verify that Field does not raise if dtype agrees
        testField = pexConfig.DictField[int, str](doc="", keytype=int, itemtype=str)
        self.assertEqual(testField.keytype, int)
        self.assertEqual(testField.itemtype, str)

    def testAssignment(self):
        c = Config1()
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "d1", {3: 3})
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "d1", {"a": 0})
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "d1", [1.2, 3, 4])
        c.d1 = None
        c.d1 = {"a": 1, "b": 2}
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "d3", {"hi": True})
        c.d3 = {4: 5}
        self.assertEqual(c.d3, {4.0: 5.0})
        d = {"a": None, "b": 4, "c": "foo"}
        c.d4 = d
        self.assertEqual(c.d4, d)
        c.d4["a"] = 12
        c.d4["b"] = "three"
        c.d4["c"] = None
        self.assertEqual(c.d4["a"], 12)
        self.assertEqual(c.d4["b"], "three")
        self.assertIsNone(c.d4["c"])
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "d4", {"hi": [1, 2, 3]})

    def testValidate(self):
        c = Config1()
        self.assertRaises(pexConfig.FieldValidationError, Config1.validate, c)

        c.d2 = {"a": "b"}
        c.validate()

    def testInPlaceModification(self):
        c = Config1()
        self.assertRaises(pexConfig.FieldValidationError, c.d1.__setitem__, 2, 0)
        self.assertRaises(pexConfig.FieldValidationError, c.d1.__setitem__, "hi", 0)
        c.d1["hi"] = 10
        self.assertEqual(c.d1, {"hi": 10})

        c.d3 = {}
        c.d3[4] = 5
        self.assertEqual(c.d3, {4.0: 5.0})

    def testNoArbitraryAttributes(self):
        c = Config1()
        self.assertRaises(pexConfig.FieldValidationError, setattr, c.d1, "should", "fail")

    def testEquality(self):
        """Test DictField.__eq__

        We create two dicts, with the keys explicitly added in a different
        order and test their equality.
        """
        keys1 = ["A", "B", "C"]
        keys2 = ["X", "Y", "Z", "a", "b", "c", "d", "e"]

        c1 = Config1()
        c1.d4 = {k: "" for k in keys1}
        for k in keys2:
            c1.d4[k] = ""

        c2 = Config1()
        for k in keys2 + keys1:
            c2.d4[k] = ""

        self.assertTrue(pexConfig.compareConfigs("test", c1, c2))

    def testNoPickle(self):
        """Test that pickle support is disabled for the proxy container."""
        c = Config1()
        with self.assertRaises(pexConfig.UnexpectedProxyUsageError):
            pickle.dumps(c.d4)


if __name__ == "__main__":
    unittest.main()
