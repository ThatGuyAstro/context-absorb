class ContextAbsorb < Formula
  desc "Cross-CLI session transfer tool for parallel AI coding sessions (Claude Code + Codex)"
  homepage "https://github.com/ThatGuyAstro/context-absorb"
  url "https://github.com/ThatGuyAstro/context-absorb/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "f97f972b48d97f23ad13978b32781f3ef1246874cda9f83016f3ba2bc9cfd0ff"
  license "MIT"
  head "https://github.com/ThatGuyAstro/context-absorb.git", branch: "main"

  depends_on "python@3.12"

  def install
    libexec.install Dir["*"]

    # Install the runtime to a stable libexec location
    bin.install_symlink libexec/"session-absorb" => "session-absorb"

    # Generate a launcher that points at the libexec runtime
    (bin/"context-absorb").write <<~EOS
      #!/bin/bash
      exec "#{Formula["python@3.12"].opt_bin}/python3" "#{libexec}/skills/shared/session_absorb_core.py" "$@"
    EOS
  end

  def caveats
    <<~EOS
      To install the runtime, shell command, and skill wrappers into ~/.local and ~/.claude / ~/.codex:

        context-absorb install --repo-root #{libexec}

      Add the optional shell alias for fast in-chat access:

        echo 'alias sa="$HOME/.local/bin/session-absorb"' >> ~/.zshrc

      The install command also registers SessionStart hooks in ~/.codex/hooks.json
      and ~/.claude/settings.json so new sessions get auto-aliased. The hook
      scripts live at ~/.local/share/session-absorb/session-start-hook-{codex,claude}.sh
      and are inspectable.
    EOS
  end

  test do
    system "#{bin}/context-absorb", "--help"
  end
end
