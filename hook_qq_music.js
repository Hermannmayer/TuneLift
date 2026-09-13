// TuneLift 解密钩子
//
// 作用：把音乐客户端的加密音频（.mflac / .mgg）还原成普通的 FLAC / OGG。
//
// 原理：QQMusicCommon.dll 导出了一个 EncAndDesMediaFile 类，客户端自己就是靠它
// 读取加密媒体的。我们不插手播放流程，而是直接把这个对象构造出来、让它打开目标
// 文件，然后把解密后的字节读出来写到指定路径。整个过程在客户端进程内完成，
// 所以必须先启动客户端。
//
// 下面这些修饰名全部来自该 DLL 的**导出表**（可用 frida 的
// Module.enumerateExports 自行核对），是二进制的接口事实；脚本的结构、命名、
// 错误处理与清理逻辑由本项目自行实现。

'use strict';

var TARGET_DLL = 'QQMusicCommon.dll';

// MSVC 的 thiscall 修饰名。逐个写全，方便对照导出表核查。
var SYMBOLS = {
  construct: '??0EncAndDesMediaFile@@QAE@XZ',
  destruct: '??1EncAndDesMediaFile@@QAE@XZ',
  open: '?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z',
  close: '?Close@EncAndDesMediaFile@@QAEXXZ',
  isOpen: '?IsOpen@EncAndDesMediaFile@@QAE_NXZ',
  size: '?GetSize@EncAndDesMediaFile@@QAEKXZ',
  read: '?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z',
};

// 对象实例需要多少字节由 DLL 自己决定，我们没法从导出表得知。
// 这里给足余量——分配少了会静默踩坏堆内存，多分配几十字节没有代价。
var INSTANCE_SIZE = 0x100; // 256 字节

// 分块读取的块大小。一次性申请整个文件大小的内存没必要，
// 30MB 以上的曲目很常见。
var CHUNK_SIZE = 4 * 1024 * 1024; // 4 MiB

function bindApi() {
  var module = Process.getModuleByName(TARGET_DLL); // 未加载时直接抛出，信息清晰
  var addr = {};
  Object.keys(SYMBOLS).forEach(function (key) {
    addr[key] = module.getExportByName(SYMBOLS[key]); // 缺失时抛出，不会静默变 null
  });

  return {
    construct: new NativeFunction(addr.construct, 'void', ['pointer'], 'thiscall'),
    destruct: new NativeFunction(addr.destruct, 'void', ['pointer'], 'thiscall'),
    open: new NativeFunction(addr.open, 'bool', ['pointer', 'pointer', 'bool', 'bool'], 'thiscall'),
    close: new NativeFunction(addr.close, 'void', ['pointer'], 'thiscall'),
    isOpen: new NativeFunction(addr.isOpen, 'bool', ['pointer'], 'thiscall'),
    size: new NativeFunction(addr.size, 'uint32', ['pointer'], 'thiscall'),
    // Read(unsigned char* buffer, unsigned long length, __int64 offset)
    read: new NativeFunction(addr.read, 'uint32', ['pointer', 'pointer', 'uint32', 'int64'], 'thiscall'),
  };
}

function readAll(api, instance, totalBytes, targetPath) {
  var file = new File(targetPath, 'wb');
  var buffer = Memory.alloc(CHUNK_SIZE);
  var written = 0;

  try {
    while (written < totalBytes) {
      var want = Math.min(CHUNK_SIZE, totalBytes - written);
      var got = api.read(instance, buffer, want, written);
      if (got === 0) {
        throw new Error('读取在偏移 ' + written + ' 处中断（期望共 ' + totalBytes + ' 字节）');
      }
      file.write(buffer.readByteArray(got));
      written += got;
    }
  } finally {
    file.close();
  }
}

rpc.exports = {
  // 由 Python 侧通过 script.exports_sync.decrypt(src, dst) 调用。
  decrypt: function (sourcePath, targetPath) {
    var api = bindApi();
    var instance = Memory.alloc(INSTANCE_SIZE);
    var opened = false;

    try {
      api.construct(instance);

      // Open(const wchar_t* path, bool, bool) —— 后两个标志沿用调用方惯例的 (1, 0)。
      if (!api.open(instance, Memory.allocUtf16String(sourcePath), 1, 0) || !api.isOpen(instance)) {
        throw new Error('无法打开源文件: ' + sourcePath);
      }
      opened = true;

      var totalBytes = api.size(instance);
      if (totalBytes === 0) {
        throw new Error('源文件大小读取失败（或为空）: ' + sourcePath);
      }

      readAll(api, instance, totalBytes, targetPath);
    } finally {
      // 无论成功还是抛错都要释放：Close 关掉文件句柄，析构释放对象内部资源。
      // 漏掉这一步会让源文件被一直占用，Windows 上连删除都会失败。
      if (opened) {
        api.close(instance);
      }
      api.destruct(instance);
    }
  },
};
