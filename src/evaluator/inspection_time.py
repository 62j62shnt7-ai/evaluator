"""Elapsed time preserves the precision supplied by the inspection headers."""
from datetime import date
from decimal import Decimal
import re


def elapsed_days(previous, current, year_days):
    if re.fullmatch(r'\d{4}-\d{2}',previous or '') and re.fullmatch(r'\d{4}-\d{2}',current or ''):
        a,b=previous.split('-'),current.split('-')
        months=(int(b[0])-int(a[0]))*12+int(b[1])-int(a[1])
        return Decimal(months)*Decimal(str(year_days))/12
    return (date.fromisoformat(current)-date.fromisoformat(previous)).days
