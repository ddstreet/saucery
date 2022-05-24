
import argparse
import logging

from . import Saucery


class SauceryArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        action = self.add_mutually_exclusive_group()
        action.add_argument('--dumpconfig', action='store_true',
                            help='Show configuration')
        self.action_group = action
        self.action_attrs = ['dumpconfig']

        self.add_argument('--saucery', help='Location of saucery')
        self.add_argument('--reductions', help='Location of reductions')
        self.add_argument('--configfile', help='Config file')
        self.add_argument('-n', '--dry-run', action='store_true',
                          help='Dry-run, do not perform actions')

        loglevel = self.add_mutually_exclusive_group()
        loglevel.add_argument('-q', '--quiet', dest='loglevel', const=logging.WARNING,
                              action='store_const',
                              help='Suppress info messages')
        loglevel.add_argument('-v', '--verbose', dest='loglevel', const=logging.DEBUG,
                              action='store_const',
                              help='Show debug messages')
        loglevel.add_argument('--loglevel', help=argparse.SUPPRESS)
        self.loglevel_group = loglevel

    def parse_args(self, *args, **kwargs):
        opts = super().parse_args(*args, **kwargs)

        opts.has_action = any([bool(getattr(opts, attr)) for attr in self.action_attrs])

        logging.basicConfig(level=opts.loglevel or logging.INFO, format='%(message)s')
        logging.getLogger(__name__).debug(f'params: {vars(opts)}')

        return opts

    def saucery(self, opts, *args, **kwargs):
        instance = Saucery(saucery=opts.saucery,
                           reductions=opts.reductions,
                           configfile=opts.configfile,
                           dry_run=opts.dry_run)

        if opts.dumpconfig:
            logging.getLogger(__name__).info(instance.dumpconfig())

        return instance