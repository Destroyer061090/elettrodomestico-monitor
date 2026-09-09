"""Configurazione pytest condivisa per i test dell'integrazione.

Abilita il plugin pytest-homeassistant-custom-component, che fornisce le
fixture standard (`hass`, `enable_custom_integrations`, ecc.) necessarie per
testare una custom integration senza un'istanza HA reale.
"""
pytest_plugins = "pytest_homeassistant_custom_component"
