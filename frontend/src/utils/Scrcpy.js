import JMuxer from 'jmuxer'

/**
 * 最小 Scrcpy 投屏实现（用于 sonic 远控 websocket -> JMuxer -> video）
 * 来自 sonic-client-web 的 Scrcpy 形态，已移除多余功能，仅保留投屏通路。
 */
export default class Scrcpy {
  constructor(props) {
    const { excuteMode } = props
    this.props = props
    this.excuteMode = excuteMode
    this.isInit = false

    this.jmuxer = null
    this.websocket = null

    this.initial(props)
    this.websocketInit(props)
    this.onPageFocus()
  }

  cmdFN(cmd) {
    if (cmd?.msg === 'size') {
      // 收到 size 后说明开始工作
      this.isInit = true
    }
  }

  initial(props) {
    if (!this.jmuxer && this.excuteMode === 'Scrcpy') {
      const { node } = props
      this.jmuxer = new JMuxer({
        node: node || 'player',
        mode: 'video',
        flushingTime: 0,
        fps: 60,
        debug: false
      })
    }
  }

  websocketInit(props) {
    if (this.websocket) return
    const { socketURL, onmessage } = props
    this.websocket = new WebSocket(socketURL)
    this.websocket.binaryType = 'arraybuffer'

    this.websocket.addEventListener('message', (event) => {
      if (typeof event.data === 'string') {
        try {
          this.cmdFN(JSON.parse(event.data))
        } catch {}
        onmessage && onmessage(event)
        return
      }

      // 二进制帧 -> JMuxer 喂流（Scrcpy 模式）
      if (typeof event.data === 'object' && this.excuteMode === 'Scrcpy') {
        if (!this.jmuxer) return
        // event.data 在浏览器可能是 ArrayBuffer
        this.jmuxer.feed({
          video: new Uint8Array(event.data)
        })
      } else {
        onmessage && onmessage(event)
      }
    })

    this.websocket.addEventListener('error', () => {
      const { onclose } = props
      onclose && onclose()
    })

    this.websocket.addEventListener('open', () => {
      // 切换运行模式（兼容 sonic 远控协议）
      this.websocket.send(
        JSON.stringify({
          type: 'switch',
          detail: this.excuteMode?.toLowerCase()
        })
      )
    })
  }

  switchMode(mode) {
    this.excuteMode = mode
    this.destroy()
    this.initial(this.props)
    this.websocket?.send(
      JSON.stringify({
        type: 'switch',
        detail: this.excuteMode?.toLowerCase()
      })
    )
    if (mode !== 'Scrcpy') {
      this.jmuxer && this.jmuxer.reset()
    }
  }

  destroy() {
    try {
      this.websocket?.close?.()
    } catch {}
    try {
      this.jmuxer && this.jmuxer.destroy && this.jmuxer.destroy()
    } catch {}
    this.jmuxer = null
    this.websocket = null
    window.onfocus = null
  }

  onPageFocus() {
    const videoDom = document.getElementById(this.props?.node || 'player')
    window.onfocus = function () {
      if (!videoDom) return
      try {
        videoDom.currentTime = Math.ceil(videoDom.buffered.end(0))
      } catch {}
    }
  }
}

