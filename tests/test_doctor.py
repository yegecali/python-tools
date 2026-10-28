import doctor


def test_tool_versions_need_the_executable_inside_bin(tmp_path):
    home = tmp_path / "jdk-21"
    (home / "bin").mkdir(parents=True)
    config = tmp_path / "java.json"
    config.write_text(f'{{"versions": {{"21": "{home.as_posix()}", "17": "{tmp_path / "nope"}"}}}}', encoding="utf-8")
    (home / "bin" / doctor.JAVA_EXE).write_text("")

    checks = {check.name: check for check in doctor.check_tool_versions("Java", config, doctor.JAVA_EXE)}

    assert checks["Java 21"].ok is True
    assert checks["Java 17"].ok is False


def test_missing_config_is_reported_not_raised(tmp_path):
    checks = doctor.check_tool_versions("Maven", tmp_path / "maven.json", doctor.MAVEN_EXE)

    assert len(checks) == 1 and checks[0].ok is False
    assert "no existe" in checks[0].detail


def test_domains_must_be_a_non_empty_list_of_strings(tmp_path):
    good = tmp_path / "domains.json"
    good.write_text('["google.com", "github.com"]', encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text('{"host": "x"}', encoding="utf-8")

    assert doctor.check_domains(good).ok is True
    assert "2 dominios" in doctor.check_domains(good).detail
    assert doctor.check_domains(bad).ok is False


def test_public_key_check_points_to_key_generation_when_missing(tmp_path):
    check = doctor.check_public_key(tmp_path / "rsa_public.pem")

    assert check.ok is False
    assert "opcion 2" in check.detail


def test_keys_are_recognised_from_their_pem_headers(rsa_key_files):
    public_path, private_path = rsa_key_files

    assert doctor.check_public_key(public_path).ok is True
    assert doctor.check_private_key(private_path).ok is True
    assert "sin passphrase" in doctor.check_private_key(private_path).detail


def test_run_checks_reports_every_item_even_when_nothing_exists(tmp_path):
    checks = doctor.run_checks(
        java_config=tmp_path / "java.json",
        maven_config=tmp_path / "maven.json",
        domains=tmp_path / "domains.json",
        public_key=tmp_path / "public.pem",
        private_key=tmp_path / "private.pem",
    )

    names = [check.name for check in checks]
    assert "Dominios" in names and "keytool" in names
    assert not any(check.ok for check in checks)
