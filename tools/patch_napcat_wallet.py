#!/usr/bin/env python3
"""给 NapCat 的 OneBot 转换器补上 walletElement -> JSON。

用法:
    python tools/patch_napcat_wallet.py "D:\AstrBot\napcat\napcat\napcat.mjs"

脚本会先备份为 napcat.mjs.bak-redalert，再插入转换器；失败可用备份还原。
"""

from __future__ import annotations

import pathlib
import sys

DEFAULT = r"D:\AstrBot\napcat\napcat\napcat.mjs"
NEEDLE = "    markdownElement: async (element) => {"
INSERT = '''    walletElement: async (element) => {
      let safe = {};
      try {
        safe = JSON.parse(JSON.stringify(element, (k, v) => typeof v === "bigint" ? v.toString() : v));
      } catch (e) {
        safe = { raw: String(element) };
      }
      return {
        type: OB11MessageDataType.json,
        data: { data: JSON.stringify({ __napcat_wallet: true, ...safe }) }
      };
    },
'''


def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    if not path.exists():
        print(f"找不到文件: {path}")
        return 1
    text = path.read_text("utf-8")
    if "walletElement: async" in text:
        print("已经打过补丁，无需重复。")
        return 0
    if NEEDLE not in text:
        print("没有找到 markdownElement 锚点，NapCat 版本可能不兼容。")
        return 2
    backup = path.with_suffix(".mjs.bak-redalert")
    if not backup.exists():
        backup.write_text(text, "utf-8")
        print(f"已备份: {backup}")
    path.write_text(text.replace(NEEDLE, INSERT + NEEDLE, 1), "utf-8")
    print("补丁完成，重启 NapCat 后生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
