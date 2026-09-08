# SPARQLWrapper-compatible Library

[![PyPI](
  <https://img.shields.io/pypi/v/rqw?color=blue>
  )](
  <https://pypi.org/project/rqw/>
) [![CI](
  <https://github.com/eggplants/rqw/actions/workflows/ci.yml/badge.svg>
  )](
  <https://github.com/eggplants/rqw/actions/workflows/ci.yml>
)

[![ghcr size](
  <https://ghcr-badge.egpl.dev/eggplants/rqw/size>
)](
  <https://github.com/eggplants/rqw/pkgs/container/rqw>
)

SPARQL Endpoint interface, compatible with SPARQLWrapper.

## Installation

```bash
# mise via github release
mise use -g github:eggplants/rqw

# mise via pipx
mise use -g pipx:rqw

# pipx
pipx install rqw

# pip
pip install rqw
```

### Docker

```bash
docker pull ghcr.io/eggplants/rqw

docker run --rm ghcr.io/eggplants/rqw eggplant
```

## CLI

```shellsession
$ rqw
Hello, world!

$ rqw eggplant
Hello, eggplant!
```

## Library

```python
import rqw

print(rqw.__version__)
```

## License

[MIT License](
  <https://github.com/eggplants/rqw/blob/master/LICENSE.txt>
)
