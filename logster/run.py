#!/usr/bin/python -tt
# -*- coding: utf-8 -*-

###
###  logster
###
###  Tails a log and applies a log parser (that knows what to do with specific)
###  types of entries in the log, then reports metrics to Ganglia and/or Graphite.
###
###  Usage:
###
###    $ logster [options] parser logfile
###
###  Help:
###
###    $ logster -h
###
###
###  Copyright 2011, Etsy, Inc.
###
###  This file is part of Logster.
###
###  Logster is free software: you can redistribute it and/or modify
###  it under the terms of the GNU General Public License as published by
###  the Free Software Foundation, either version 3 of the License, or
###  (at your option) any later version.
###
###  Logster is distributed in the hope that it will be useful,
###  but WITHOUT ANY WARRANTY; without even the implied warranty of
###  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
###  GNU General Public License for more details.
###
###  You should have received a copy of the GNU General Public License
###  along with Logster. If not, see <http://www.gnu.org/licenses/>.
###
###  Forked from the ganglia-logtailer project
###  (http://bitbucket.org/maplebed/ganglia-logtailer):
###    Copyright Linden Research, Inc. 2008
###    Released under the GPL v2 or later.
###    For a full description of the license, please visit
###    http://www.gnu.org/licenses/gpl.txt
###

from __future__ import with_statement

import os
import sys
import re
import optparse
import stat
import logging.handlers
import fcntl
import socket
import traceback
import contextlib

from time import time
from math import floor

try:
    import importlib
except ImportError:
    pass # Python 2.6

# Local dependencies
from logster.logster_helper import LogsterParsingException, LockingError

# Globals
gmetric = "/usr/bin/gmetric"

logger = logging.getLogger('logster')

def get_args():
    "Parse command-line options"

    # defaults
    logtail = "/usr/sbin/logtail2"
    state_dir = "/var/run"

    cmdline = optparse.OptionParser(usage="usage: %prog [options] parser logfile",
        description="Tail a log file and filter each line to generate metrics that can be sent to common monitoring packages.")
    cmdline.add_option('--logtail', action='store', default=logtail,
                        help='Specify location of logtail.  Default %s' % logtail)
    cmdline.add_option('--metric-prefix', '-p', action='store',
                        help='Add prefix to all published metrics. This is for people that may multiple instances of same service on same host.',
                        default='')
    cmdline.add_option('--metric-suffix', '-x', action='store',
                        help='Add suffix to all published metrics. This is for people that may add suffix at the end of their metrics.',
                        default=None)
    cmdline.add_option('--parser-help', action='store_true',
                        help='Print usage and options for the selected parser')
    cmdline.add_option('--parser-options', action='store',
                        help='Options to pass to the logster parser such as "-o VALUE --option2 VALUE". These are parser-specific and passed directly to the parser.')
    cmdline.add_option('--gmetric-options', action='store',
                        help='Options to pass to gmetric such as "-d 180 -c /etc/ganglia/gmond.conf" (default). These are passed directly to gmetric.',
                        default='-d 180 -c /etc/ganglia/gmond.conf')
    cmdline.add_option('--graphite-host', action='store',
                        help='Hostname and port for Graphite collector, e.g. graphite.example.com:2003')
    cmdline.add_option('--state-dir', '-s', action='store', default=state_dir,
                        help='Where to store the logtail state file.  Default location %s' % state_dir)
    cmdline.add_option('--output', '-o', action='append',
                       choices=('graphite', 'ganglia', 'stdout'),
                       help="Where to send metrics (can specify multiple times). Choices are 'graphite', 'ganglia', or 'stdout'.")
    cmdline.add_option('--stdout-separator', action='store', default="_", dest="stdout_separator",
                        help='Seperator between prefix/suffix and name for stdout. Default is \"%default\".')
    cmdline.add_option('--dry-run', '-d', action='store_true', default=False,
                        help='Parse the log file but send stats to standard output.')
    cmdline.add_option('--debug', '-D', action='store_true', default=False,
                        help='Provide more verbose logging for debugging.')
    cmdline.add_option('--log', default="/var/log/logster",
                       help="directory to which to log (or 'stderr')")
    options, arguments = cmdline.parse_args()

    if options.parser_help:
        options.parser_options = '-h'

    if (len(arguments) != 2):
        cmdline.print_help()
        cmdline.error("Supply at least two arguments: parser and logfile.")
    if not options.output:
        cmdline.print_help()
        cmdline.error("Supply where the data should be sent with -o (or --output).")
    if 'graphite' in options.output and not options.graphite_host:
        cmdline.print_help()
        cmdline.error("You must supply --graphite-host when using 'graphite' as an output type.")

    class_name, log_file = arguments
    return class_name, log_file, options


def setup_logging(options):
    """
    Configure the Logging infrastructure for use througout logster
    Uses appending log file, rotated at 100MB, keeping 5.
    """
    format = '%(levelname)-8s %(message)s'
    if options.log == 'stderr':
        hdlr = logging.StreamHandler(sys.stderr)
    else:
        format = '%(asctime)s ' + format
        log_dir = options.log
        if (not os.path.isdir(log_dir)):
            os.mkdir(log_dir)
        hdlr = logging.handlers.RotatingFileHandler('%s/logster.log' % log_dir, 'a', 100 * 1024 * 1024, 5)
    formatter = logging.Formatter(format)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.INFO)

    if options.debug:
        logger.setLevel(logging.DEBUG)


## This provides a lineno() function to make it easy to grab the line
## number that we're on (for logging)
## Danny Yoo (dyoo@hkn.eecs.berkeley.edu)
## taken from http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/145297
import inspect
def lineno():
    """Returns the current line number in our program."""
    return inspect.currentframe().f_back.f_lineno


def submit_stats(parser, duration, options):
    metrics = parser.get_state(duration)

    if 'ganglia' in options.output:
        submit_ganglia(metrics, options)
    if 'graphite' in options.output:
        submit_graphite(metrics, options)
    if 'stdout' in options.output:
        submit_stdout(metrics, options)

def submit_stdout(metrics, options):
    for metric in metrics:
        if (options.metric_prefix != ""):
            metric.name = options.metric_prefix + options.stdout_separator + metric.name
        if (options.metric_suffix is not None):
            metric.name = metric.name + options.stdout_separator + options.metric_suffix
        sys.stdout.write("%s %s\n" % (metric.name, metric.value))

def submit_ganglia(metrics, options):
    for metric in metrics:

        if (options.metric_prefix != ""):
            metric.name = options.metric_prefix + "_" + metric.name
        if (options.metric_suffix is not None):
            metric.name = metric.name + "_" + options.metric_suffix

        gmetric_cmd = "%s %s --name %s --value %s --type %s --units \"%s\"" % (
            gmetric, options.gmetric_options, metric.name, metric.value, metric.type, metric.units)
        logger.debug("Submitting Ganglia metric: %s" % gmetric_cmd)

        if (not options.dry_run):
            os.system("%s" % gmetric_cmd)
        else:
            sys.stdout.write("%s\n" % gmetric_cmd)


def submit_graphite(metrics, options):
    if (re.match("^[\w\.\-]+\:\d+$", options.graphite_host) == None):
        raise Exception("Invalid host:port found for Graphite: '%s'" % options.graphite_host)

    if (not options.dry_run):
        host = options.graphite_host.split(':')
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host[0], int(host[1])))

    for metric in metrics:

        if (options.metric_prefix != ""):
            metric.name = options.metric_prefix + "." + metric.name
        if (options.metric_suffix is not None):
            metric.name = metric.name + "." + options.metric_suffix

        metric_string = "%s %s %s" % (metric.name, metric.value, metric.timestamp)
        logger.debug("Submitting Graphite metric: %s" % metric_string)

        if (not options.dry_run):
            s.send("%s\n" % metric_string)
        else:
            sys.stdout.write("%s %s\n" % (options.graphite_host,
                metric_string))

    if (not options.dry_run):
        s.close()


def start_locking(lockfile_name):
    """ Acquire a lock via a provided lockfile filename. """
    if os.path.exists(lockfile_name):
        raise LockingError("Lock file already exists.")

    f = open(lockfile_name, 'w')

    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.write("%s" % os.getpid())
    except IOError:
        # Would be better to also check the pid in the lock file and remove the
        # lock file if that pid no longer exists in the process table.
        raise LockingError("Cannot acquire logster lock (%s)" % lockfile_name)

    logger.debug("Locking successful")
    return f


def end_locking(lockfile_fd, lockfile_name):
    """ Release a lock via a provided file descriptor. """
    try:
        fcntl.flock(lockfile_fd, fcntl.LOCK_UN | fcntl.LOCK_NB)
    except IOError:
        raise LockingError("Cannot release logster lock (%s)" % lockfile_name)

    try:
        os.unlink(lockfile_name)
    except OSError:
        raise LockingError("Cannot unlink %s" % lockfile_name)

    logger.debug("Unlocking successful")
    return


@contextlib.contextmanager
def lock_context(lockfile_name):
    """
    Check for lock file so multiple copies of the same parser aren't run
    simultaneously, as will happen if the log parsing takes more time than the
    cron period, which is likely on the first run if the logfile is huge.
    """
    try:
        lockfile = start_locking(lockfile_name)
    except LockingError:
        logger.warning("Failed to get lock. Is another instance of logster running?")
        raise SystemExit(1)
    try:
        yield lockfile
    finally:
        end_locking(lockfile, lockfile_name)

        # try to remove the lockfile one last time, but it's a valid state that it's already been removed.
        try:
            end_locking(lockfile, lockfile_name)
        except Exception:
            pass

def import_module(module_name):
    if 'importlib' not in globals():
        # Python 2.6 compatibility
        return __import__(module_name, fromlist=['__name__'])
    return importlib.import_module(module_name)

def load_parser(class_name, *args, **kwargs):
    """
    Given a class name, find the parser by that name. Module may be specified
    if prefixed by ':'. By default, the module will be
    'logster.parsers.{class_name}'.
    """
    module, sep, class_name = class_name.rpartition(':')
    module = module or 'logster.parsers.%(class_name)s' % vars()

    # Import the module and instantiate the indicated class.
    module = import_module(module)
    return getattr(module, class_name)(*args, **kwargs)


def main():
    script_start_time = time()

    class_name, log_file, options = get_args()
    setup_logging(options)

    dirsafe_logfile = log_file.replace('/','-')
    logtail_state_file = '%s/logtail-%s%s.state' % (options.state_dir, class_name, dirsafe_logfile)
    logtail_lock_file = '%s/logtail-%s%s.lock' % (options.state_dir, class_name, dirsafe_logfile)
    shell_tail = "%s -f %s -o %s" % (options.logtail, log_file, logtail_state_file)

    logger.info("Executing parser %s on logfile %s" % (class_name, log_file))
    logger.debug("Using state file %s" % logtail_state_file)

    parser = load_parser(class_name, option_string=options.parser_options)

    with lock_context(logtail_lock_file):

        # Get input to parse.
        try:

            # Read the age of the state file to see how long it's been since we last
            # ran. Replace the state file if it has gone missing. While we are her,
            # touch the state file to reset the time in case logtail doesn't
            # find any new lines (and thus won't update the statefile).
            try:
                state_file_age = os.stat(logtail_state_file)[stat.ST_MTIME]

                # Calculate now() - state file age to determine check duration.
                duration = floor(time()) - floor(state_file_age)
                logger.debug("Setting duration to %s seconds." % duration)

            except OSError:
                logger.info('Writing new state file and exiting. (Was either first run, or state file went missing.)')
                input = os.popen(shell_tail)
                retval = input.close()
                if (retval != 256):
                    logger.warning('%s returned bad exit code %s' % (shell_tail, retval))
                sys.exit(0)

            # Open a pipe to read input from logtail.
            input = os.popen(shell_tail)

        except Exception:
            e = sys.exc_info()[1]
            # note - there is no exception when logtail doesn't exist.
            # I don't know when this exception will ever actually be triggered.
            sys.stdout.write(
                "Failed to run %s to get log data (line %s): %s\n" %
                (shell_tail, lineno(), e))
            sys.exit(1)

        # Parse each line from input, then send all stats to their collectors.
        try:
            for line in input:
                try:
                    parser.parse_line(line)
                except LogsterParsingException:
                    e = sys.exc_info()[1]
                    # This should only catch recoverable exceptions (of which there
                    # aren't any at the moment).
                    logger.debug("Parsing exception caught at %s: %s" % (lineno(), e))

            submit_stats(parser, duration, options)

        except Exception:
            e = sys.exc_info()[1]
            sys.stdout.write("Exception caught at %s: %s\n" % (lineno(), e))
            traceback.print_exc()
            sys.exit(1)

        # Log the execution time
        exec_time = round(time() - script_start_time, 1)
        logger.info("Total execution time: %s seconds." % exec_time)

        # Set mtime and atime for the state file to the startup time of the script
        # so that the cron interval is not thrown off by parsing a large number of
        # log entries.
        os.utime(logtail_state_file, (floor(script_start_time), floor(script_start_time)))

if __name__ == '__main__':
    main()
