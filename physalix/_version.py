"""Source unique de la version applicative (indépendante du format projet)."""

__version_info__ = (1, 10, 1)
__channel__ = ""
__base_version__ = ".".join(map(str, __version_info__))
__version__ = f"{__base_version__}-{__channel__}" if __channel__ else __base_version__
__development__ = __channel__ == "dev"
