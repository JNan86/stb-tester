#!/usr/bin/python

# Copyright 2014-2017 Stb-tester.com Ltd.
# Copyright 2013 YouView TV Ltd.
# License: LGPL v2.1 or (at your option) any later version (see
# https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).

"""Run static analysis over the specified stb-tester python scripts.

"stbt lint" runs "pylint" with the following additional checkers:

* E7001: The image path given to "stbt.match" (and similar functions)
  does not exist on disk.
* E7002: The return value from is_screen_black, match, match_text, ocr,
  press_and_wait, or wait_until isn't used (perhaps you've forgotten to
  use "assert").
* E7003: The argument given to "wait_until" must be a callable (such as
  a function or lambda expression).
* E7004: FrameObject properties must always provide "self._frame" as the
  "frame" parameter to functions such as "stbt.match".
* E7005: The image path given to "stbt.match" (and similar functions)
  exists on disk, but isn't committed to git.
* E7006: FrameObject properties must use "self._frame", not
  "stbt.get_frame()".
* E7007: FrameObject properties must not have side-effects that change
  the state of the device-under-test by calling "stbt.press()" or
  "stbt.press_and_wait()".
* E7008: "assert True" has no effect.

"""
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import argparse
import re
import os
import subprocess
import sys
import threading


def main(argv):
    parser = argparse.ArgumentParser(
        prog="stbt lint",
        usage="stbt lint [--help] [pylint options] filename [filename...]",
        description=__doc__,
        epilog="Any other command-line arguments are passed through to pylint.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    _, pylint_args = parser.parse_known_args(argv[1:])

    if not pylint_args:
        parser.print_usage(sys.stderr)
        return 1

    if sys.version_info.major == 2:
        executable_name = "pylint"
    else:
        executable_name = "pylint3"

    try:
        with open("/dev/null", "w") as devnull:
            subprocess.check_call([executable_name, "--help"],
                                  stdout=devnull, stderr=devnull)
    except OSError as e:
        if e.errno == 2:
            sys.stderr.write(
                "stbt lint: error: Couldn't find '%s' executable\n"
                % executable_name)
            return 1

    pylint = subprocess.Popen(
        [executable_name, "--load-plugins=_stbt.pylint_plugin"] + pylint_args,
        stderr=subprocess.PIPE)

    t = threading.Thread(target=filter_warnings,
                         args=(pylint.stderr,
                               os.fdopen(sys.stderr.fileno(), "wb", 0)))
    t.start()

    pylint.wait()
    t.join()
    return pylint.returncode


def filter_warnings(input_, output):
    while True:
        line = input_.readline()
        if not line:
            break
        if any(re.search(pattern, line) for pattern in WARNINGS):
            continue
        output.write(line)


WARNINGS = [
    # pylint:disable=line-too-long
    br"libdc1394 error: Failed to initialize libdc1394",
    br"pygobject_register_sinkfunc is deprecated",
    br"assertion .G_TYPE_IS_BOXED \(boxed_type\). failed",
    br"assertion .G_IS_PARAM_SPEC \(pspec\). failed",
    br"return isinstance\(object, \(type, types.ClassType\)\)",
    br"return isinstance\(object, type\)",
    br"gsignal.c:.*: parameter 1 of type '<invalid>' for signal \".*\" is not a value type",
    br"astroid.* Use gi.require_version",
    br"^  __import__\(m\)$",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
