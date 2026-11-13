"""Connector catalogue. CSV import is not a remote system and is handled by `csv_import`."""

from operon.modules.integrations.connectors.odoo import OdooConnector
from operon.modules.integrations.connectors.shopify import ShopifyConnector

REMOTE_CONNECTORS = {c.key: c for c in (OdooConnector, ShopifyConnector)}
