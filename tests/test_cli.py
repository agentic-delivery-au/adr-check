from hello_world.cli import main


def test_main_writes_the_greeting_to_stdout(capsys):
    exit_code = main(["Ada"])

    assert exit_code == 0
    assert capsys.readouterr().out == "Hello, Ada!\n"


def test_main_passes_a_custom_greeting_through(capsys):
    exit_code = main(["Ada", "--greeting", "Hi"])

    assert exit_code == 0
    assert capsys.readouterr().out == "Hi, Ada!\n"


def test_main_reports_a_blank_name_on_stderr(capsys):
    exit_code = main(["   "])

    assert exit_code == 1
    assert "must not be blank" in capsys.readouterr().err
