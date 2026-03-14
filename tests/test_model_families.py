"""Tests for model family detection."""
from comfy_mcp.builder.families import detect_family, family_defaults, FAMILIES

class TestDetectFamily:
    def test_sd15_explicit(self):
        f = detect_family("v1-5-pruned-emaonly.safetensors")
        assert f.name == "sd1.5"
        assert f.default_width == 512

    def test_sd15_dreamshaper(self):
        assert detect_family("dreamshaper_8.safetensors").name == "sd1.5"

    def test_sd15_deliberate(self):
        assert detect_family("deliberate_v3.safetensors").name == "sd1.5"

    def test_sdxl_explicit(self):
        f = detect_family("sd_xl_base_1.0.safetensors")
        assert f.name == "sdxl"
        assert f.default_width == 1024

    def test_sdxl_juggernaut(self):
        assert detect_family("juggernautXL_v9.safetensors").name == "sdxl"

    def test_sdxl_dreamshaperxl(self):
        assert detect_family("dreamshaperXL_v2.safetensors").name == "sdxl"

    def test_sdxl_pony(self):
        assert detect_family("ponyDiffusionV6.safetensors").name == "sdxl"

    def test_flux(self):
        f = detect_family("flux1-dev.safetensors")
        assert f.name == "flux"
        assert f.default_cfg == 1.0

    def test_flux_pro(self):
        assert detect_family("flux-pro-v1.safetensors").name == "flux"

    def test_unknown_defaults_to_sd15(self):
        f = detect_family("some_random_model.safetensors")
        assert f.name == "sd1.5"

    def test_empty_string_defaults_to_sd15(self):
        assert detect_family("").name == "sd1.5"

class TestFamilyDefaults:
    def test_returns_dict(self):
        d = family_defaults("sd_xl_base_1.0.safetensors")
        assert d["family"] == "sdxl"
        assert d["width"] == 1024
        assert d["height"] == 1024
        assert d["cfg"] == 7.0
        assert d["steps"] == 25

    def test_flux_low_cfg(self):
        d = family_defaults("flux1-dev.safetensors")
        assert d["cfg"] == 1.0
        assert d["scheduler"] == "simple"
