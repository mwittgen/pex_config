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


def isSorted(theList):
    if len(theList) <= 1:
        return True

    p = theList[0]
    for x in theList[1:]:
        if x < p:
            return False
        p = x
    return True


def isPositive(x):
    return x > 0


class Config1(pexConfig.Config):
    l1 = pexConfig.ListField("l1", int, minLength=2, maxLength=5, default=[1, 2, 3], itemCheck=isPositive)
    l2 = pexConfig.ListField("l2", int, length=3, default=[1, 2, 3], listCheck=isSorted, itemCheck=isPositive)
    l3 = pexConfig.ListField("l3", int, length=3, default=None, optional=True, itemCheck=isPositive)
    l4 = pexConfig.ListField("l4", int, length=3, default=None, itemCheck=isPositive)


class Config2(pexConfig.Config):
    lf = pexConfig.ListField("lf", float, default=[1, 2, 3])
    ls = pexConfig.ListField("ls", str, default=["hi"])


class ListFieldTest(unittest.TestCase):
    def testConstructor(self):
        try:

            class BadDtype(pexConfig.Config):
                ll = pexConfig.ListField("...", list)

        except Exception:
            pass
        else:
            raise SyntaxError("Unsupported dtype ListFields should not be allowed")

        try:

            class BadLengths(pexConfig.Config):
                ll = pexConfig.ListField("...", int, minLength=4, maxLength=2)

        except ValueError:
            pass
        else:
            raise SyntaxError("minLnegth <= maxLength should not be allowed")

        try:

            class BadLength(pexConfig.Config):
                ll = pexConfig.ListField("...", int, length=-1)

        except Exception:
            pass
        else:
            raise SyntaxError("negative length should not be allowed")

        try:

            class BadLength2(pexConfig.Config):
                ll = pexConfig.ListField("...", int, maxLength=-1)

        except Exception:
            pass
        else:
            raise SyntaxError("negative max length should not be allowed")

    def testAssignment(self):
        c = Config1()
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l1", [1.2, 3, 4])
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l1", [-1, -2, -3])
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l1", [1, 2, 0])
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l1", [1, 2, None])
        c.l1 = None
        c.l1 = [1, 1]
        c.l1 = [1, 1, 1]
        c.l1 = [1, 1, 1, 1]
        c.l1 = [1, 1, 1, 1, 1]

        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l2", [1, 2, None])
        c.l2 = None
        c.l2 = [1, 2, 3]

        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l3", [0, 3, 2])
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l3", [1, 2, None])
        c.l3 = None
        c.l3 = [1, 1, 1]

        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l4", [0, 3, 2])
        self.assertRaises(pexConfig.FieldValidationError, setattr, c, "l4", [1, 2, None])
        c.l4 = None
        c.l4 = [1, 1, 1]

    def testValidate(self):
        c = Config1()
        self.assertRaises(pexConfig.FieldValidationError, Config1.validate, c)

        c.l4 = [1, 2, 3]
        c.validate()

    def testInPlaceModification(self):
        c = Config1()
        self.assertRaises(pexConfig.FieldValidationError, c.l1.__setitem__, 2, 0)
        c.l1[2] = 10
        self.assertEqual(c.l1, [1, 2, 10])
        self.assertEqual((1, 2, 10), c.l1)

        c.l1.insert(2, 20)
        self.assertEqual(c.l1, [1, 2, 20, 10])
        c.l1.append(30)
        self.assertEqual(c.l1, [1, 2, 20, 10, 30])
        c.l1.extend([4, 5, 6])
        self.assertEqual(c.l1, [1, 2, 20, 10, 30, 4, 5, 6])

    def testCastAndTypes(self):
        c = Config2()
        self.assertEqual(c.lf, [1.0, 2.0, 3.0])

        c.lf[2] = 10
        self.assertEqual(c.lf, [1.0, 2.0, 10.0])

        c.ls.append("foo")
        self.assertEqual(c.ls, ["hi", "foo"])

    def testNoArbitraryAttributes(self):
        c = Config1()
        self.assertRaises(pexConfig.FieldValidationError, setattr, c.l1, "should", "fail")

    def testNoPickle(self):
        """Test that pickle support is disabled for the proxy container."""
        c = Config2()
        with self.assertRaises(pexConfig.UnexpectedProxyUsageError):
            pickle.dumps(c.ls)


if __name__ == "__main__":
    unittest.main()
