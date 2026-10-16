# -*- coding: utf-8 -*-
"""見た目の型。名前 → 作り方。"""
from .motion import Motion
from .chalk import Chalk
from .notebook import Notebook

LOOKS = {Motion.name: Motion, Chalk.name: Chalk, Notebook.name: Notebook}
