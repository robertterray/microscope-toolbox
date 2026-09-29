#!/usr/bin/env python3

# Imports
import argparse
import logging
import yaml
import os

from microscope_toolbox import main

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    logging.basicConfig(level=logging.INFO)

    argparser.add_argument(
        "--list_argument",
        help="Type in a space separated list here",
        type=str,
        nargs="+",
    )
    argparser.add_argument(
        "--boolean_argument",
        help="If you supply this without any arguments it will be set to True",
        default=False,
        action="store_true",
    )
    argparser.add_argument(
        "--string_argument",
        help="This should be any string",
        default="default",
    )

    args = argparser.parse_args()

    logger.info(os.environ["ANALYSIS_BUCKET"])
    logger.info(os.environ["PHOTOMETRY_BUCKET"])
    logger.info(os.environ["ENVIRONMENT"])
    logger.info(os.environ["DATABASE"])

    main.do_stuff(args.list_argument, args.boolean_argument, args.string_argument)
