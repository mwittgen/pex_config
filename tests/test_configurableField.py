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

import lsst.pex.config as pexConf


class Config1(pexConf.Config):
    f = pexConf.Field("f", dtype=float, default=5, check=lambda x: x > 0)


class Target1:
    ConfigClass = Config1

    def __init__(self, config):
        self.f = config.f


def Target2(config):
    return config.f


class Config2(pexConf.Config):
    c1 = pexConf.ConfigurableField("c1", target=Target1)
    c2 = pexConf.ConfigurableField("c2", target=Target2, ConfigClass=Config1, default=Config1(f=3))


class ConfigurableFieldTest(unittest.TestCase):
    def testConstructor(self):
        try:

            class BadTarget(pexConf.Config):
                d = pexConf.ConfigurableField("...", target=None)

        except Exception:
            pass
        else:
            raise SyntaxError("Uncallable targets should not be allowed")

        try:

            class NoConfigClass(pexConf.Config):
                d = pexConf.ConfigurableField("...", target=Target2)

        except Exception:
            pass
        else:
            raise SyntaxError("Missing ConfigClass should not be allowed")

        try:

            class BadConfigClass(pexConf.Config):
                d = pexConf.DictField("...", target=Target2, ConfigClass=Target2)

        except Exception:
            pass
        else:
            raise SyntaxError("ConfigClass that are not subclasses of Config should not be allowed")

    def testBasics(self):
        c = Config2()
        self.assertEqual(c.c1.f, 5)
        self.assertEqual(c.c2.f, 3)

        self.assertEqual(type(c.c1.apply()), Target1)
        self.assertEqual(c.c1.apply().f, 5)
        self.assertEqual(c.c2.apply(), 3)

        c.c2.retarget(Target1)
        self.assertEqual(c.c2.f, 3)
        self.assertEqual(type(c.c2.apply()), Target1)
        self.assertEqual(c.c2.apply().f, 3)

        c.c1.f = 2
        self.assertEqual(c.c1.f, 2)
        self.assertRaises(pexConf.FieldValidationError, setattr, c.c1, "f", 0)

        c.c1 = Config1(f=10)
        self.assertEqual(c.c1.f, 10)

        c.c1 = Config1
        self.assertEqual(c.c1.f, 5)

        f = Config2(**dict(c.items()))
        self.assertEqual(f.c1.f, c.c1.f)
        self.assertEqual(f.c1.target, c.c1.target)
        self.assertEqual(f.c2.target, c.c2.target)
        self.assertEqual(f.c2.f, c.c2.f)

        c.c2.f = 1
        c.c1.f = 100
        f.update(**dict(c.items()))
        self.assertEqual(f.c1.f, c.c1.f)
        self.assertEqual(f.c1.target, c.c1.target)
        self.assertEqual(f.c2.target, c.c2.target)
        self.assertEqual(f.c2.f, c.c2.f)

    def testValidate(self):
        c = Config2()
        self.assertRaises(pexConf.FieldValidationError, setattr, c.c1, "f", 0)

        c.validate()

    def testPersistence(self):
        c = Config2()
        c.c2.retarget(Target1)
        c.c2.f = 10
        c.save("test.py")

        r = Config2()
        r.load("test.py")
        os.remove("test.py")

        self.assertEqual(c.c2.f, r.c2.f)
        self.assertEqual(c.c2.target, r.c2.target)

    def testNoPickle(self):
        """Test that pickle support is disabled for the proxy container."""
        c = Config2()
        with self.assertRaises(pexConf.UnexpectedProxyUsageError):
            pickle.dumps(c.c2)


if __name__ == "__main__":
    unittest.main()
