# AutoCetacean v0.4.0 Verification Record

目标：让**陌生人**从零装上就能看到价值，不靠 API key、不靠网络、不靠第三方包。

## 1. 新增内容
- `src/autocetacean/demo.py`：`run_demo()` / `main()`，在临时目录里跑两个自包含场景并打印人类可读证明
- `src/autocetacean/cli.py`：新增 `autocetacean demo [--json]` 子命令
- `src/autocetacean/mcp_proxy.py`：记录器把子进程 stderr 交给不支持 `fileno()` 的捕获流时会崩，改为优雅退化到 `DEVNULL`（`_subprocess_stderr_target`）
- `tests/test_demo.py`：3 个测试（demo 报告、`--json` 退出码与字段、人类输出含 PASS 行、且不在当前目录留脏文件）
- `README.md`：新增「See it work in 60 seconds」小节
- `pyproject.toml` / `src/autocetacean/__init__.py`：版本 `0.4.0`

## 2. 全量测试
```text
============================= test session starts ==============================
platform linux -- Python 3.11.2, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/fish/projects/autocetacean
configfile: pyproject.toml
testpaths: tests
plugins: platformdirs-4.14.5, asyncio-1.4.1.post1, lazy-fixtures-1.4.1, mock-3.17.0, anyio-4.16.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 95 items

tests/test_checkpoint.py ....                                            [  4%]
tests/test_cli.py ....                                                   [  8%]
tests/test_demo.py ...                                                   [ 11%]
tests/test_extended_coverage.py ..........                               [ 22%]
tests/test_graph.py .......                                              [ 29%]
tests/test_layers.py ................                                    [ 46%]
tests/test_ledger.py ...........                                         [ 57%]
tests/test_mcp_proxy.py ..                                               [ 60%]
tests/test_replay.py ........                                            [ 68%]
tests/test_schema_violation.py .......                                   [ 75%]
tests/test_v02_features.py ..........                                    [ 86%]
tests/test_visualizer.py .........                                       [ 95%]
tests/test_workspace_guard.py ....                                       [100%]

============================== 95 passed in 0.75s ==============================
```

## 3. 干净 venv + 本地 wheel 安装验证
环境：`python3 -m venv /tmp/ac_v04_venv`，`pip install --no-index --find-links=<repo>/dist autocetacean==0.4.0`
（**没有任何 PYTHONPATH，也没有仓库在 sys.path 上**）

```text
$ /tmp/ac_v04_venv/bin/autocetacean --version
autocetacean 0.4.0

$ cd /tmp && /tmp/ac_v04_venv/bin/autocetacean demo
AutoCetacean demo — two guarantees, one command, no external dependencies

[PASS] workspace_guard_rollback
       gate exit code: 1
       rolled back:    True
       changed files:  {'added': ['junk.txt'], 'modified': ['calc.py'], 'deleted': []}
       junk removed:   True
       restored:       'return a + b'

[PASS] mcp_record_and_offline_replay
       recorded exchanges: 2
       replayed value:     12
       drift error code:   -32602
       mismatches caught:  1

AutoCetacean demo: ALL CHECKS PASSED (guard rollback + mcp replay)

EXIT=0
```

## 4. 构建产物
- `dist/autocetacean-0.4.0-py3-none-any.whl` — 41271 bytes
- `dist/autocetacean-0.4.0.tar.gz` — 52546 bytes

## 5. 从公共 GitHub URL 安装（真实用户路径，v0.4.0 tag 推送后实测）
```bash
python3 -m venv /tmp/ac_v04_pub
/tmp/ac_v04_pub/bin/pip install "autocetacean @ git+https://github.com/xunWhale/autocetacean@v0.4.0"
cd /tmp && /tmp/ac_v04_pub/bin/autocetacean --version   # autocetacean 0.4.0
cd /tmp && /tmp/ac_v04_pub/bin/autocetacean demo
```

```text
AutoCetacean demo — two guarantees, one command, no external dependencies

[PASS] workspace_guard_rollback
       gate exit code: 1
       rolled back:    True
       changed files:  {'added': ['junk.txt'], 'modified': ['calc.py'], 'deleted': []}
       junk removed:   True
       restored:       'return a + b'

[PASS] mcp_record_and_offline_replay
       recorded exchanges: 2
       replayed value:     12
       drift error code:   -32602
       mismatches caught:  1

AutoCetacean demo: ALL CHECKS PASSED (guard rollback + mcp replay)

EXIT=0
```

即：文档里写给陌生人的那条命令，在本机从公开仓库全新装一遍后确实跑通，
且 `demo` 是在 `/tmp`（不在仓库目录、无 PYTHONPATH）下执行的。
