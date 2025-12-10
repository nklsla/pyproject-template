def template() -> str:
    out = ["This", "is", "a", "template"]
    return "Python project template! {out}".format(out=" ".join(out))


if __name__ == "__main__":
    print(template())
