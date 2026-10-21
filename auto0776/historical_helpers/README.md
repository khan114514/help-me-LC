# 历史资产处理参考

model_assets.py 和 install_assets_stream.py来自旧OneDC作者侧实现，源字节保留。前者建立白名单模型资产manifest，后者校验流式模型包并导入旧镜像路径。

它们不启动研究、不验证当前平台/卡型，不含模型凭据。install_assets_stream.py仍假定旧容器路径和下载方式；使用前阅读，改成新平台支持的可信构建路径。不要向脚本argv传带密钥/签名的临时下载URL，不把服务暴露给Actor。

没有复制旧model_gateway/bootstrap凭据提取器，因为其路由与用户当前Coding Plan规则不一致。接手按handoff/04实现或使用已验证的新可信网关，不恢复旧网关。
