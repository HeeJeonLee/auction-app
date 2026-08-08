from tests import test_analysis

failed = []
for name in dir(test_analysis):
    if name.startswith("test_"):
        try:
            getattr(test_analysis, name)()
            print(f"{name}: OK")
        except AssertionError as e:
            print(f"{name}: FAIL (AssertionError): {e}
")
            failed.append(name)
        except Exception as e:
            print(f"{name}: ERROR: {e}")
            failed.append(name)

if failed:
    raise SystemExit(1)
else:
    print("All tests passed")
    raise SystemExit(0)
