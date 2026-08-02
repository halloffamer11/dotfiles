return {
  -- Active theme: duskfox (a nightfox variant)
  { "EdenEast/nightfox.nvim", lazy = false, priority = 1000 },

  -- Installed alternates — preview/switch anytime via <leader>uC.
  -- catppuccin + tokyonight already ship with LazyVim.
  {
    "sainnhe/gruvbox-material",
    lazy = false,
    priority = 999,
    config = function()
      -- gruvbox-material configures via vim.g globals, not a setup() call
      vim.g.gruvbox_material_background = "medium" -- soft | medium | hard
      vim.g.gruvbox_material_foreground = "material" -- material | mix | original
      vim.g.gruvbox_material_better_performance = 1
    end,
  },

  { "LazyVim/LazyVim", opts = { colorscheme = "duskfox" } },
}
