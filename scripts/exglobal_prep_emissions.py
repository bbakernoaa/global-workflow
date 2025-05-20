#!/usr/bin/env python3
"""
exglobal_prep_emissions.py

This script creates an emissions object which performs the pre-processing
for aerosol emissions.

The script performs the following steps:
1. Initializes a logger
2. Reads configuration from environment variables
3. Creates an AerosolEmissions object
4. Executes the aerosol emissions pre-processing workflow

Parameters
----------
Environment Variables:
    Various configuration parameters read from the environment
    (processed by cast_strdict_as_dtypedict)
    LOGGING_LEVEL : str, optional
        Logging level (default: "DEBUG")

Notes
-----
This script is executed as part of the global forecast system
workflow for aerosol emissions pre-processing.

Examples
--------
$ python exglobal_prep_emissions.py
"""
import os

from wxflow import Logger, cast_strdict_as_dtypedict
from pygfs import AerosolEmissions


# Initialize root logger with configurable level from environment
logger = Logger(
    level=os.environ.get("LOGGING_LEVEL", "DEBUG"),  # Use DEBUG level by default
    colored_log=True  # Enable colored log output for better readability
)


if __name__ == '__main__':

    # Take configuration from environment and cast it as python dictionary
    config = cast_strdict_as_dtypedict(os.environ)
    print(config)

    # Instantiate the emissions pre-processing task
    emissions = AerosolEmissions(config)

    # Initialize the task (typically sets up necessary variables)
    emissions.initialize()

    # Configure the task (typically loads configuration parameters)
    emissions.configure()

    # Execute the main processing task
    emissions.execute()

    # Finalize and clean up resources
    emissions.finalize()
