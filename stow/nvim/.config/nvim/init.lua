-- bootstrap lazy.nvim, LazyVim and your plugins
require("config.lazy")
vim.opt.scrolloff = 8
vim.keymap.set("n", "<C-d>", "<C-d>zz")
vim.keymap.set("n", "<C-u>", "<C-u>zz")
