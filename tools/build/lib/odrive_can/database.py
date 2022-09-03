import cantools
import sys
import re

try:
    import importlib.resources as pkg_resources
except ImportError:
    import importlib_resources as pkg_resources

if sys.version_info < (3, 9):
    from typing import List
else:
    List = list

with pkg_resources.open_text("odrive_can", "odrive-cansimple.dbc") as db_file:
    db = cantools.database.load(db_file)

streamed_messages: List[str] = [
    "Heartbeat",
    "Get_Encoder_Estimates"
]


def format_name(messageName: str, removeVerb: bool = False) -> str:
    if removeVerb and re.match("^[GS]et_", messageName):
        messageName = messageName[4:]
    return "_".join(word if word.isupper() else word.lower() for word in messageName.split("_"))


def unformat_name(pythonName: str) -> str:
    return "_".join((word[0].upper() + word[1:] for word in pythonName.split("_")))
