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
  -- ── Calm rendering ──────────────────────────────────────────────────────────
  -- One visual signal per role. render-markdown's default paints six differently
  -- hued full-width bars behind headings; that plus colour plus bold plus the '#'
  -- is four signals saying one thing. Here the hierarchy is a brightness ramp on
  -- the heading text alone, bold is weight rather than colour, and inline code is
  -- a faint block and nothing else.
  --
  -- Colours are derived from whichever theme is loaded (Normal/Comment/heading fg)
  -- rather than hardcoded, so switching theme via <leader>uC keeps this working.
  {
    "MeanderingProgrammer/render-markdown.nvim",
    optional = true,
    opts = {
      heading = {
        sign = false,
        icons = {}, -- leave the literal '#' markers visible
        width = "block",
        -- Six entries required: render-markdown clamps this list, so a shorter one
        -- would hand every deeper heading the last entry's background.
        backgrounds = { "MdNoBg", "MdNoBg", "MdNoBg", "MdNoBg", "MdNoBg", "MdNoBg" },
        foregrounds = {
          "RenderMarkdownH1",
          "RenderMarkdownH2",
          "RenderMarkdownH3",
          "RenderMarkdownH4",
          "RenderMarkdownH5",
          "RenderMarkdownH6",
        },
      },
    },
  },
  {
    "LazyVim/LazyVim",
    -- `init`, never `config`: LazyVim's own spec is opts-only, so lazy.nvim runs the
    -- default handler require("lazyvim").setup(opts). A `config` here would replace
    -- that handler and the distro would never initialise.
    init = function()
      -- alpha is the weight of `a`; both args are 24-bit ints.
      local function blend(a, b, alpha)
        local function chan(shift)
          local x = math.floor(a / 2 ^ shift) % 256
          local y = math.floor(b / 2 ^ shift) % 256
          return math.floor(x * alpha + y * (1 - alpha) + 0.5)
        end
        return chan(16) * 0x10000 + chan(8) * 0x100 + chan(0)
      end

      local function fg_of(group)
        local ok, hl = pcall(vim.api.nvim_get_hl, 0, { name = group, link = false })
        return (ok and hl.fg) or nil
      end

      local function paint()
        local ok, normal = pcall(vim.api.nvim_get_hl, 0, { name = "Normal", link = false })
        if not ok then
          return
        end
        local light = vim.o.background == "light"
        local bg = normal.bg or (light and 0xffffff or 0x000000)
        local fg = normal.fg or (light and 0x000000 or 0xffffff)
        local muted = fg_of("Comment") or blend(fg, bg, 0.55)
        local accent = fg_of("@markup.heading.1.markdown") or fg_of("Function") or fg

        local set = vim.api.nvim_set_hl
        set(0, "MdNoBg", {}) -- intentionally empty: kills the heading bars

        -- H1 keeps the theme's accent; the ramp walks to body text by H3 and fades
        -- to comment grey by H6, so depth reads as weight the way print does.
        local ramp = {
          { fg = accent, bold = true },
          { fg = blend(accent, fg, 0.55), bold = true },
          { fg = fg, bold = true },
          { fg = blend(fg, muted, 0.5), bold = true },
          { fg = muted, bold = true },
          { fg = muted },
        }
        for level, spec in ipairs(ramp) do
          set(0, "RenderMarkdownH" .. level, spec)
          set(0, "@markup.heading." .. level .. ".markdown", spec)
        end

        set(0, "@markup.strong", { fg = fg, bold = true }) -- weight, not colour
        set(0, "@markup.italic", { italic = true })
        set(0, "@markup.raw.markdown_inline", { fg = fg }) -- the block is the signal
        set(0, "RenderMarkdownCodeInline", { bg = blend(muted, bg, 0.18) })
        set(0, "RenderMarkdownCode", { bg = blend(muted, bg, 0.10) })
        for _, group in ipairs({ "RenderMarkdownBullet", "RenderMarkdownDash", "RenderMarkdownQuote" }) do
          set(0, group, { fg = muted })
        end
      end

      vim.api.nvim_create_autocmd("ColorScheme", {
        group = vim.api.nvim_create_augroup("markdown_calm", { clear = true }),
        callback = paint,
      })
      paint() -- the colorscheme has already loaded by the time this runs
    end,
  },
}
