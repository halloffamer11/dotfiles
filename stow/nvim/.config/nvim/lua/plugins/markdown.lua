-- lang.markdown extra minus style enforcement: keep marksman, render-markdown,
-- and the browser preview; drop markdownlint diagnostics and the markdown
-- format-on-save chain (prettier / markdownlint-cli2 / markdown-toc).
-- Fast-capture notes — no style-nagging (see devops CLAUDE.md decisions).
return {
  {
    "mfussenegger/nvim-lint",
    optional = true,
    opts = function(_, opts)
      if opts.linters_by_ft then
        opts.linters_by_ft.markdown = nil
        opts.linters_by_ft["markdown.mdx"] = nil
      end
    end,
  },
  {
    "stevearc/conform.nvim",
    optional = true,
    opts = function(_, opts)
      if opts.formatters_by_ft then
        opts.formatters_by_ft.markdown = nil
        opts.formatters_by_ft["markdown.mdx"] = nil
      end
    end,
  },
}
