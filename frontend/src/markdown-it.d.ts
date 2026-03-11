declare module 'markdown-it' {
  interface MarkdownIt {
    render(src: string): string
  }
  interface Options {
    html?: boolean
    breaks?: boolean
    linkify?: boolean
  }
  const MarkdownIt: {
    new (options?: Options): MarkdownIt
  }
  export default MarkdownIt
}
