import logging
from typing import Any, Dict

from pygfs.ufswm.gfs import GFS
from wxflow import Task

logger = logging.getLogger(__name__.split(".")[-1])


class GFSForecast(Task):
    """
    UFS-weather-model forecast task for the GFS
    """

    def __init__(self, config: Dict[str, Any], *args, **kwargs):
        """
        Parameters
        ----------
        config : Dict
                 dictionary object containing configuration from environment

        *args : tuple
                Additional arguments to `Task`

        **kwargs : dict, optional
                   Extra keyword arguments to `Task`
        """

        super().__init__(config, *args, **kwargs)

        # Create and initialize the GFS variant of the UFS
        self.gfs = GFS(config)
