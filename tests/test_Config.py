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

import io
import itertools
import os
import pickle
import re
import unittest

try:
    import yaml
except ImportError:
    yaml = None

import lsst.pex.config as pexConfig

# Some tests depend on daf_base.
# Skip them if it is not found.
try:
    import lsst.daf.base as dafBase
except ImportError:
    dafBase = None

GLOBAL_REGISTRY = {}


class Simple(pexConfig.Config):
    i = pexConfig.Field("integer test", int, optional=True)
    f = pexConfig.Field("float test", float, default=3.0)
    b = pexConfig.Field("boolean test", bool, default=False, optional=False)
    c = pexConfig.ChoiceField(
        "choice test", str, default="Hello", allowed={"Hello": "First choice", "World": "second choice"}
    )
    r = pexConfig.RangeField("Range test", float, default=3.0, optional=False, min=3.0, inclusiveMin=True)
    ll = pexConfig.ListField(
        "list test", int, default=[1, 2, 3], maxLength=5, itemCheck=lambda x: x is not None and x > 0
    )
    d = pexConfig.DictField(
        "dict test", str, str, default={"key": "value"}, itemCheck=lambda x: x.startswith("v")
    )
    n = pexConfig.Field("nan test", float, default=float("NAN"))


GLOBAL_REGISTRY["AAA"] = Simple


class InnerConfig(pexConfig.Config):
    f = pexConfig.Field("Inner.f", float, default=0.0, check=lambda x: x >= 0, optional=False)


GLOBAL_REGISTRY["BBB"] = InnerConfig


class OuterConfig(InnerConfig, pexConfig.Config):
    i = pexConfig.ConfigField("Outer.i", InnerConfig)

    def __init__(self):
        pexConfig.Config.__init__(self)
        self.i.f = 5.0

    def validate(self):
        pexConfig.Config.validate(self)
        if self.i.f < 5:
            raise ValueError("validation failed, outer.i.f must be greater than 5")


class Complex(pexConfig.Config):
    c = pexConfig.ConfigField("an inner config", InnerConfig)
    r = pexConfig.ConfigChoiceField(
        "a registry field", typemap=GLOBAL_REGISTRY, default="AAA", optional=False
    )
    p = pexConfig.ConfigChoiceField("another registry", typemap=GLOBAL_REGISTRY, default="BBB", optional=True)


class Deprecation(pexConfig.Config):
    old = pexConfig.Field("Something.", int, default=10, deprecated="not used!")


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.simple = Simple()
        self.inner = InnerConfig()
        self.outer = OuterConfig()
        self.comp = Complex()
        self.deprecation = Deprecation()

    def tearDown(self):
        del self.simple
        del self.inner
        del self.outer
        del self.comp

    def testFieldTypeAnnotationRuntime(self):
        # test parsing type annotation for runtime dtype
        testField = pexConfig.Field[str](doc="")
        self.assertEqual(testField.dtype, str)

        # verify that forward references work correctly
        testField = pexConfig.Field["float"](doc="")
        self.assertEqual(testField.dtype, float)

        # verify that Field rejects multiple types
        with self.assertRaises(ValueError):
            pexConfig.Field[str, int](doc="")  # type: ignore

        # verify that Field raises in conflict with dtype:
        with self.assertRaises(ValueError):
            pexConfig.Field[str](doc="", dtype=int)

        # verify that Field does not raise if dtype agrees
        testField = pexConfig.Field[int](doc="", dtype=int)
        self.assertEqual(testField.dtype, int)

    def testInit(self):
        self.assertIsNone(self.simple.i)
        self.assertEqual(self.simple.f, 3.0)
        self.assertFalse(self.simple.b)
        self.assertEqual(self.simple.c, "Hello")
        self.assertEqual(list(self.simple.ll), [1, 2, 3])
        self.assertEqual(self.simple.d["key"], "value")
        self.assertEqual(self.inner.f, 0.0)
        self.assertEqual(self.deprecation.old, 10)

        self.assertEqual(self.deprecation._fields["old"].doc, "Something. Deprecated: not used!")

        self.assertEqual(self.outer.i.f, 5.0)
        self.assertEqual(self.outer.f, 0.0)

        self.assertEqual(self.comp.c.f, 0.0)
        self.assertEqual(self.comp.r.name, "AAA")
        self.assertEqual(self.comp.r.active.f, 3.0)
        self.assertEqual(self.comp.r["BBB"].f, 0.0)

    def testDeprecationWarning(self):
        """Test that a deprecated field emits a warning when it is set."""
        with self.assertWarns(FutureWarning) as w:
            self.deprecation.old = 5
            self.assertEqual(self.deprecation.old, 5)

            self.assertIn(self.deprecation._fields["old"].deprecated, str(w.warnings[-1].message))

    def testDeprecationOutput(self):
        """Test that a deprecated field is not written out unless it is set."""
        stream = io.StringIO()
        self.deprecation.saveToStream(stream)
        self.assertNotIn("config.old", stream.getvalue())
        with self.assertWarns(FutureWarning):
            self.deprecation.old = 5
        stream = io.StringIO()
        self.deprecation.saveToStream(stream)
        self.assertIn("config.old=5\n", stream.getvalue())

    def testValidate(self):
        self.simple.validate()

        self.inner.validate()
        self.assertRaises(ValueError, setattr, self.outer.i, "f", -5)
        self.outer.i.f = 10.0
        self.outer.validate()

        try:
            self.simple.d["failKey"] = "failValue"
        except pexConfig.FieldValidationError:
            pass
        except Exception:
            raise "Validation error Expected"
        self.simple.validate()

        self.outer.i = InnerConfig
        self.assertRaises(ValueError, self.outer.validate)
        self.outer.i = InnerConfig()
        self.assertRaises(ValueError, self.outer.validate)

        self.comp.validate()
        self.comp.r = None
        self.assertRaises(ValueError, self.comp.validate)
        self.comp.r = "BBB"
        self.comp.validate()

    def testRangeFieldConstructor(self):
        """Test RangeField constructor's checking of min, max"""
        val = 3
        self.assertRaises(ValueError, pexConfig.RangeField, "", int, default=val, min=val, max=val - 1)
        self.assertRaises(ValueError, pexConfig.RangeField, "", float, default=val, min=val, max=val - 1e-15)
        for inclusiveMin, inclusiveMax in itertools.product((False, True), (False, True)):
            if inclusiveMin and inclusiveMax:
                # should not raise
                class Cfg1(pexConfig.Config):
                    r1 = pexConfig.RangeField(
                        doc="",
                        dtype=int,
                        default=val,
                        min=val,
                        max=val,
                        inclusiveMin=inclusiveMin,
                        inclusiveMax=inclusiveMax,
                    )
                    r2 = pexConfig.RangeField(
                        doc="",
                        dtype=float,
                        default=val,
                        min=val,
                        max=val,
                        inclusiveMin=inclusiveMin,
                        inclusiveMax=inclusiveMax,
                    )

                Cfg1()
            else:
                # raise while constructing the RangeField (hence cannot make
                # it part of a Config)
                self.assertRaises(
                    ValueError,
                    pexConfig.RangeField,
                    doc="",
                    dtype=int,
                    default=val,
                    min=val,
                    max=val,
                    inclusiveMin=inclusiveMin,
                    inclusiveMax=inclusiveMax,
                )
                self.assertRaises(
                    ValueError,
                    pexConfig.RangeField,
                    doc="",
                    dtype=float,
                    default=val,
                    min=val,
                    max=val,
                    inclusiveMin=inclusiveMin,
                    inclusiveMax=inclusiveMax,
                )

    def testRangeFieldDefault(self):
        """Test RangeField's checking of the default value"""
        minVal = 3
        maxVal = 4
        for val, inclusiveMin, inclusiveMax, shouldRaise in (
            (minVal, False, True, True),
            (minVal, True, True, False),
            (maxVal, True, False, True),
            (maxVal, True, True, False),
        ):

            class Cfg1(pexConfig.Config):
                r = pexConfig.RangeField(
                    doc="",
                    dtype=int,
                    default=val,
                    min=minVal,
                    max=maxVal,
                    inclusiveMin=inclusiveMin,
                    inclusiveMax=inclusiveMax,
                )

            class Cfg2(pexConfig.Config):
                r2 = pexConfig.RangeField(
                    doc="",
                    dtype=float,
                    default=val,
                    min=minVal,
                    max=maxVal,
                    inclusiveMin=inclusiveMin,
                    inclusiveMax=inclusiveMax,
                )

        if shouldRaise:
            self.assertRaises(pexConfig.FieldValidationError, Cfg1)
            self.assertRaises(pexConfig.FieldValidationError, Cfg2)
        else:
            Cfg1()
            Cfg2()

    def testSave(self):
        self.comp.r = "BBB"
        self.comp.p = "AAA"
        self.comp.c.f = 5.0
        self.comp.save("roundtrip.test")

        roundTrip = Complex()
        roundTrip.load("roundtrip.test")
        os.remove("roundtrip.test")
        self.assertEqual(self.comp.c.f, roundTrip.c.f)
        self.assertEqual(self.comp.r.name, roundTrip.r.name)
        del roundTrip

        # test saving to an open file
        with open("roundtrip.test", "w") as outfile:
            self.comp.saveToStream(outfile)
        roundTrip = Complex()
        with open("roundtrip.test", "r") as infile:
            roundTrip.loadFromStream(infile)
        os.remove("roundtrip.test")
        self.assertEqual(self.comp.c.f, roundTrip.c.f)
        self.assertEqual(self.comp.r.name, roundTrip.r.name)
        del roundTrip

        # test saving to a string.
        saved_string = self.comp.saveToString()
        roundTrip = Complex()
        roundTrip.loadFromString(saved_string)
        self.assertEqual(self.comp.c.f, roundTrip.c.f)
        self.assertEqual(self.comp.r.name, roundTrip.r.name)
        del roundTrip

        # Test an override of the default variable name.
        with open("roundtrip.test", "w") as outfile:
            self.comp.saveToStream(outfile, root="root")
        roundTrip = Complex()
        with self.assertRaises(NameError):
            roundTrip.load("roundtrip.test")
        roundTrip.load("roundtrip.test", root="root")
        os.remove("roundtrip.test")
        self.assertEqual(self.comp.c.f, roundTrip.c.f)
        self.assertEqual(self.comp.r.name, roundTrip.r.name)

    def testDuplicateRegistryNames(self):
        self.comp.r["AAA"].f = 5.0
        self.assertEqual(self.comp.p["AAA"].f, 3.0)

    def testInheritance(self):
        class AAA(pexConfig.Config):
            a = pexConfig.Field("AAA.a", int, default=4)

        class BBB(AAA):
            b = pexConfig.Field("BBB.b", int, default=3)

        class CCC(BBB):
            c = pexConfig.Field("CCC.c", int, default=2)

        # test multi-level inheritance
        c = CCC()
        self.assertIn("a", c.toDict())
        self.assertEqual(c._fields["a"].dtype, int)
        self.assertEqual(c.a, 4)

        # test conflicting multiple inheritance
        class DDD(pexConfig.Config):
            a = pexConfig.Field("DDD.a", float, default=0.0)

        class EEE(DDD, AAA):
            pass

        e = EEE()
        self.assertEqual(e._fields["a"].dtype, float)
        self.assertIn("a", e.toDict())
        self.assertEqual(e.a, 0.0)

        class FFF(AAA, DDD):
            pass

        f = FFF()
        self.assertEqual(f._fields["a"].dtype, int)
        self.assertIn("a", f.toDict())
        self.assertEqual(f.a, 4)

        # test inheritance from non Config objects
        class GGG:
            a = pexConfig.Field("AAA.a", float, default=10.0)

        class HHH(GGG, AAA):
            pass

        h = HHH()
        self.assertEqual(h._fields["a"].dtype, float)
        self.assertIn("a", h.toDict())
        self.assertEqual(h.a, 10.0)

        # test partial Field redefinition

        class III(AAA):
            pass

        III.a.default = 5

        self.assertEqual(III.a.default, 5)
        self.assertEqual(AAA.a.default, 4)

    @unittest.skipIf(dafBase is None, "lsst.daf.base is required")
    def testConvertPropertySet(self):
        ps = pexConfig.makePropertySet(self.simple)
        self.assertFalse(ps.exists("i"))
        self.assertEqual(ps.getScalar("f"), self.simple.f)
        self.assertEqual(ps.getScalar("b"), self.simple.b)
        self.assertEqual(ps.getScalar("c"), self.simple.c)
        self.assertEqual(list(ps.getArray("ll")), list(self.simple.ll))

        ps = pexConfig.makePropertySet(self.comp)
        self.assertEqual(ps.getScalar("c.f"), self.comp.c.f)

    def testFreeze(self):
        self.comp.freeze()

        self.assertRaises(pexConfig.FieldValidationError, setattr, self.comp.c, "f", 10.0)
        self.assertRaises(pexConfig.FieldValidationError, setattr, self.comp, "r", "AAA")
        self.assertRaises(pexConfig.FieldValidationError, setattr, self.comp, "p", "AAA")
        self.assertRaises(pexConfig.FieldValidationError, setattr, self.comp.p["AAA"], "f", 5.0)

    def checkImportRoundTrip(self, importStatement, searchString, shouldBeThere):
        self.comp.c.f = 5.0

        # Generate a Config through loading
        stream = io.StringIO()
        stream.write(str(importStatement))
        self.comp.saveToStream(stream)
        roundtrip = Complex()
        roundtrip.loadFromStream(stream.getvalue())
        self.assertEqual(self.comp.c.f, roundtrip.c.f)

        # Check the save stream
        stream = io.StringIO()
        roundtrip.saveToStream(stream)
        self.assertEqual(self.comp.c.f, roundtrip.c.f)
        streamStr = stream.getvalue()
        if shouldBeThere:
            self.assertTrue(re.search(searchString, streamStr))
        else:
            self.assertFalse(re.search(searchString, streamStr))

    def testImports(self):
        # A module not used by anything else, but which exists
        importing = "import lsst.pex.config._doNotImportMe\n"
        self.checkImportRoundTrip(importing, importing, True)

    def testBadImports(self):
        dummy = "somethingThatDoesntExist"
        importing = (
            """
try:
    import %s
except ImportError:
    pass
"""
            % dummy
        )
        self.checkImportRoundTrip(importing, dummy, False)

    def testPickle(self):
        self.simple.f = 5
        simple = pickle.loads(pickle.dumps(self.simple))
        self.assertIsInstance(simple, Simple)
        self.assertEqual(self.simple.f, simple.f)

        self.comp.c.f = 5
        comp = pickle.loads(pickle.dumps(self.comp))
        self.assertIsInstance(comp, Complex)
        self.assertEqual(self.comp.c.f, comp.c.f)

    @unittest.skipIf(yaml is None, "Test requires pyyaml")
    def testYaml(self):
        self.simple.f = 5
        simple = yaml.safe_load(yaml.dump(self.simple))
        self.assertIsInstance(simple, Simple)
        self.assertEqual(self.simple.f, simple.f)

        self.comp.c.f = 5
        # Use a different loader to check that it also works
        comp = yaml.load(yaml.dump(self.comp), Loader=yaml.FullLoader)
        self.assertIsInstance(comp, Complex)
        self.assertEqual(self.comp.c.f, comp.c.f)

    def testCompare(self):
        comp2 = Complex()
        inner2 = InnerConfig()
        simple2 = Simple()
        self.assertTrue(self.comp.compare(comp2))
        self.assertTrue(comp2.compare(self.comp))
        self.assertTrue(self.comp.c.compare(inner2))
        self.assertTrue(self.simple.compare(simple2))
        self.assertTrue(simple2.compare(self.simple))
        self.assertEqual(self.simple, simple2)
        self.assertEqual(simple2, self.simple)
        outList = []

        def outFunc(msg):
            outList.append(msg)

        simple2.b = True
        simple2.ll.append(4)
        simple2.d["foo"] = "var"
        self.assertFalse(self.simple.compare(simple2, shortcut=True, output=outFunc))
        self.assertEqual(len(outList), 1)
        del outList[:]
        self.assertFalse(self.simple.compare(simple2, shortcut=False, output=outFunc))
        output = "\n".join(outList)
        self.assertIn("Inequality in b", output)
        self.assertIn("Inequality in size for ll", output)
        self.assertIn("Inequality in keys for d", output)
        del outList[:]
        self.simple.d["foo"] = "vast"
        self.simple.ll.append(5)
        self.simple.b = True
        self.simple.f += 1e8
        self.assertFalse(self.simple.compare(simple2, shortcut=False, output=outFunc))
        output = "\n".join(outList)
        self.assertIn("Inequality in f", output)
        self.assertIn("Inequality in ll[3]", output)
        self.assertIn("Inequality in d['foo']", output)
        del outList[:]
        comp2.r["BBB"].f = 1.0  # changing the non-selected item shouldn't break equality
        self.assertTrue(self.comp.compare(comp2))
        comp2.r["AAA"].i = 56  # changing the selected item should break equality
        comp2.c.f = 1.0
        self.assertFalse(self.comp.compare(comp2, shortcut=False, output=outFunc))
        output = "\n".join(outList)
        self.assertIn("Inequality in c.f", output)
        self.assertIn("Inequality in r['AAA']", output)
        self.assertNotIn("Inequality in r['BBB']", output)

        # Before DM-16561, this incorrectly returned `True`.
        self.assertFalse(self.inner.compare(self.outer))
        # Before DM-16561, this raised.
        self.assertFalse(self.outer.compare(self.inner))

    def testLoadError(self):
        """Check that loading allows errors in the file being loaded to
        propagate.
        """
        self.assertRaises(SyntaxError, self.simple.loadFromStream, "bork bork bork")
        self.assertRaises(NameError, self.simple.loadFromStream, "config.f = bork")

    def testNames(self):
        """Check that the names() method returns valid keys.

        Also check that we have the right number of keys, and as they are
        all known to be valid we know that we got them all.
        """

        names = self.simple.names()
        self.assertEqual(len(names), 8)
        for name in names:
            self.assertTrue(hasattr(self.simple, name))

    def testIteration(self):
        self.assertIn("ll", self.simple)
        self.assertIn("ll", self.simple.keys())
        self.assertIn("Hello", self.simple.values())
        self.assertEqual(len(self.simple.values()), 8)

        for k, v, (k1, v1) in zip(self.simple.keys(), self.simple.values(), self.simple.items()):
            self.assertEqual(k, k1)
            if k == "n":
                self.assertNotEqual(v, v1)
            else:
                self.assertEqual(v, v1)


if __name__ == "__main__":
    unittest.main()
