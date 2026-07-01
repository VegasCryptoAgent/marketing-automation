/* @ds-bundle: {"format":3,"namespace":"TrendPilotAIDesignSystem_1ab598","components":[{"name":"DropZone","sourcePath":"components/content/DropZone.jsx"},{"name":"TrendCard","sourcePath":"components/content/TrendCard.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Tag","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"GlassCard","sourcePath":"components/core/GlassCard.jsx"},{"name":"ProgressStepper","sourcePath":"components/feedback/ProgressStepper.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"Spinner","sourcePath":"components/feedback/Toast.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Textarea","sourcePath":"components/forms/Input.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Switch.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"}],"sourceHashes":{"components/content/DropZone.jsx":"b73e347f9a93","components/content/TrendCard.jsx":"6a5a58adfaab","components/core/Badge.jsx":"e718e65c5a98","components/core/Button.jsx":"eb4b3deb3d60","components/core/GlassCard.jsx":"8164cc21adc7","components/feedback/ProgressStepper.jsx":"682cdb02d25e","components/feedback/Toast.jsx":"6ee87eacbc4e","components/forms/Input.jsx":"f950dcdaae75","components/forms/Select.jsx":"3c30f7566829","components/forms/Switch.jsx":"b53d00b44855","components/navigation/Tabs.jsx":"d3c9f07542b1"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.TrendPilotAIDesignSystem_1ab598 = window.TrendPilotAIDesignSystem_1ab598 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/content/DropZone.jsx
try { (() => {
const {
  useState
} = React;
/**
 * DropZone — dashed drag-and-drop upload target. Source: .drop-zone.
 */
function DropZone({
  label = 'Drag & drop your file here',
  sublabel = 'or click to browse local files',
  onFiles,
  icon
}) {
  const [dragOver, setDragOver] = useState(false);
  return /*#__PURE__*/React.createElement("div", {
    onDragOver: e => {
      e.preventDefault();
      setDragOver(true);
    },
    onDragLeave: () => setDragOver(false),
    onDrop: e => {
      e.preventDefault();
      setDragOver(false);
      onFiles && onFiles(e.dataTransfer.files);
    },
    style: {
      border: `2px dashed ${dragOver ? 'var(--primary-color)' : 'rgba(255,255,255,0.15)'}`,
      borderRadius: 'var(--radius-md)',
      padding: '2.5rem 1.5rem',
      textAlign: 'center',
      cursor: 'pointer',
      transition: 'var(--transition-normal)',
      background: dragOver ? 'rgba(139, 92, 246, 0.04)' : 'rgba(255,255,255,0.01)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      color: dragOver ? 'var(--primary-color)' : 'var(--text-secondary)',
      marginBottom: '1rem',
      transition: 'var(--transition-fast)'
    }
  }, icon), /*#__PURE__*/React.createElement("p", {
    style: {
      fontWeight: 500,
      fontSize: '0.95rem',
      marginBottom: '0.25rem',
      color: 'var(--text-primary)'
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.8rem',
      color: 'var(--text-secondary)'
    }
  }, sublabel));
}
Object.assign(__ds_scope, { DropZone });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/content/DropZone.jsx", error: String((e && e.message) || e) }); }

// components/content/TrendCard.jsx
try { (() => {
/**
 * TrendCard — selectable list-item card for scanned trends / curated campaign
 * concepts. Source: .campaign-selector-card + .campaign-thumbnail.
 */
function TrendCard({
  thumbnail,
  title,
  subtitle,
  platform,
  active = false,
  onClick
}) {
  return /*#__PURE__*/React.createElement("div", {
    onClick: onClick,
    style: {
      background: active ? 'rgba(139, 92, 246, 0.08)' : 'rgba(255,255,255,0.02)',
      border: `1px solid ${active ? 'var(--primary-color)' : 'var(--border-color)'}`,
      borderRadius: 'var(--radius-md)',
      padding: '0.8rem',
      cursor: 'pointer',
      display: 'flex',
      gap: '1rem',
      boxShadow: active ? '0 0 15px rgba(139, 92, 246, 0.15)' : 'none',
      transition: 'var(--transition-normal)'
    }
  }, thumbnail && /*#__PURE__*/React.createElement("img", {
    src: thumbnail,
    alt: "",
    style: {
      width: 70,
      height: 70,
      borderRadius: 6,
      objectFit: 'cover',
      border: '1px solid var(--border-color)',
      flexShrink: 0
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      gap: '0.25rem',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("h4", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: '0.95rem',
      margin: 0,
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      color: 'var(--text-primary)'
    }
  }, title), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '0.75rem',
      color: 'var(--text-secondary)',
      margin: 0,
      display: '-webkit-box',
      WebkitLineClamp: 2,
      WebkitBoxOrient: 'vertical',
      overflow: 'hidden'
    }
  }, subtitle), platform && /*#__PURE__*/React.createElement("span", {
    style: {
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid var(--border-color)',
      borderRadius: 4,
      padding: '0.15rem 0.4rem',
      fontSize: '0.7rem',
      fontWeight: 600,
      color: 'var(--primary-color)',
      width: 'fit-content'
    }
  }, platform)));
}
Object.assign(__ds_scope, { TrendCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/content/TrendCard.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
/**
 * Badge / Tag — small status or category pill.
 * Badge = uppercase, tinted (source: .badge). Tag = neutral rounded pill (source: .tag).
 */
function Badge({
  children,
  tone = 'primary',
  style
}) {
  const tones = {
    primary: {
      background: 'var(--badge-primary-bg)',
      border: '1px solid var(--badge-primary-border)',
      color: 'var(--badge-primary-text)'
    },
    success: {
      background: 'var(--badge-success-bg)',
      border: '1px solid transparent',
      color: 'var(--badge-success-text)'
    },
    error: {
      background: 'var(--badge-error-bg)',
      border: '1px solid transparent',
      color: 'var(--badge-error-text)'
    }
  };
  return /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.75rem',
      padding: '0.25rem 0.6rem',
      borderRadius: '10px',
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
      fontFamily: 'var(--font-body)',
      ...tones[tone],
      ...style
    }
  }, children);
}
function Tag({
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 'var(--radius-pill)',
      padding: '0.3rem 0.8rem',
      fontSize: '0.8rem',
      color: 'var(--text-primary)',
      display: 'inline-block',
      ...style
    }
  }, children);
}
Object.assign(__ds_scope, { Badge, Tag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Button — primary / secondary / icon / text variants from the source app's
 * .primary-btn / .secondary-btn / .icon-btn / .text-btn classes.
 */
function Button({
  children,
  variant = 'primary',
  glow = false,
  disabled = false,
  size = 'md',
  icon = null,
  onClick,
  style,
  ...rest
}) {
  const sizePad = size === 'sm' ? '0.5rem 1rem' : size === 'lg' ? '1rem' : '0.8rem 1.8rem';
  const fontSize = size === 'sm' ? '0.8rem' : '1rem';
  const base = {
    border: 'none',
    borderRadius: 'var(--radius-md)',
    fontFamily: 'var(--font-display)',
    fontWeight: 600,
    fontSize,
    padding: sizePad,
    cursor: disabled ? 'not-allowed' : 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    transition: 'var(--transition-normal)'
  };
  let variantStyle = {};
  if (variant === 'primary') {
    variantStyle = disabled ? {
      background: '#374151',
      color: '#9ca3af',
      opacity: 0.5
    } : {
      background: 'var(--primary-grad)',
      color: '#fff',
      boxShadow: glow ? 'var(--shadow-glow-primary)' : 'none'
    };
  } else if (variant === 'secondary') {
    variantStyle = {
      background: 'rgba(255,255,255,0.06)',
      color: 'var(--text-primary)',
      border: '1px solid var(--border-color)'
    };
  } else if (variant === 'icon') {
    variantStyle = {
      background: 'rgba(255,255,255,0.05)',
      color: 'var(--text-primary)',
      border: '1px solid var(--border-color)',
      fontWeight: 500
    };
  } else if (variant === 'text') {
    variantStyle = {
      background: 'none',
      color: 'var(--error-color)',
      fontWeight: 500,
      fontSize: '0.9rem',
      textDecoration: 'underline',
      fontFamily: 'var(--font-body)'
    };
  }
  return /*#__PURE__*/React.createElement("button", _extends({
    onClick: disabled ? undefined : onClick,
    disabled: disabled,
    style: {
      ...base,
      ...variantStyle,
      ...style
    },
    onMouseEnter: e => {
      if (disabled) return;
      if (variant === 'primary') {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.filter = 'brightness(1.1)';
        e.currentTarget.style.boxShadow = 'var(--shadow-glow-primary)';
      } else if (variant === 'secondary' || variant === 'icon') {
        e.currentTarget.style.background = 'rgba(255,255,255,0.12)';
        e.currentTarget.style.borderColor = variant === 'icon' ? 'var(--primary-color)' : 'rgba(255,255,255,0.2)';
      } else if (variant === 'text') {
        e.currentTarget.style.color = '#ff6b8b';
      }
    },
    onMouseLeave: e => {
      if (disabled) return;
      if (variant === 'primary') {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.filter = 'none';
        e.currentTarget.style.boxShadow = glow ? 'var(--shadow-glow-primary)' : 'none';
      } else if (variant === 'secondary' || variant === 'icon') {
        e.currentTarget.style.background = variant === 'icon' ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.06)';
        e.currentTarget.style.borderColor = 'var(--border-color)';
      } else if (variant === 'text') {
        e.currentTarget.style.color = 'var(--error-color)';
      }
    }
  }, rest), icon, children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/GlassCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * GlassCard — the app's single most-used surface: translucent dark fill,
 * blur, hairline border, soft black shadow. Everything sits on this.
 */
function GlassCard({
  children,
  padded = true,
  hoverable = true,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      background: 'var(--surface-card)',
      backdropFilter: 'var(--blur-card)',
      WebkitBackdropFilter: 'var(--blur-card)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-card)',
      padding: padded ? '2rem' : 0,
      transition: 'var(--transition-normal)',
      ...style
    },
    onMouseEnter: e => {
      if (hoverable) e.currentTarget.style.borderColor = 'var(--surface-card-hover-border)';
    },
    onMouseLeave: e => {
      if (hoverable) e.currentTarget.style.borderColor = 'var(--border-color)';
    }
  }, rest), children);
}
Object.assign(__ds_scope, { GlassCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/GlassCard.jsx", error: String((e && e.message) || e) }); }

// components/feedback/ProgressStepper.jsx
try { (() => {
/**
 * ProgressStepper — pipeline-progress bar + numbered step list.
 * Source: .progress-bar-container / .stepper / .step.active / .step.completed.
 */
function ProgressStepper({
  percent = 0,
  statusMessage,
  steps
}) {
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'rgba(255,255,255,0.05)',
      height: 6,
      borderRadius: 3,
      overflow: 'hidden',
      marginBottom: '0.5rem'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--primary-grad)',
      height: '100%',
      width: `${percent}%`,
      transition: 'width 0.4s ease'
    }
  })), statusMessage && /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '0.85rem',
      color: 'var(--text-secondary)',
      marginBottom: '1.5rem',
      fontStyle: 'italic'
    }
  }, statusMessage), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '1.2rem'
    }
  }, steps.map((step, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '1rem',
      opacity: step.state === 'pending' ? 0.35 : step.state === 'completed' ? 0.7 : 1,
      transition: 'var(--transition-normal)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: '50%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontWeight: 600,
      fontSize: '0.85rem',
      border: '1px solid var(--border-color)',
      background: step.state === 'active' ? 'var(--primary-grad)' : step.state === 'completed' ? 'var(--success-color)' : 'rgba(255,255,255,0.08)',
      borderColor: step.state === 'active' || step.state === 'completed' ? 'transparent' : 'var(--border-color)',
      boxShadow: step.state === 'active' ? 'var(--shadow-glow-primary)' : 'none',
      color: step.state === 'completed' ? 'white' : 'var(--text-primary)'
    }
  }, i + 1), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '0.9rem',
      fontWeight: 500
    }
  }, step.label)))));
}
Object.assign(__ds_scope, { ProgressStepper });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/ProgressStepper.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
/**
 * Toast — bottom-right transient notification. Source: .toast + toastUp keyframe.
 */
function Toast({
  message,
  tone = 'success',
  visible = true
}) {
  if (!visible) return null;
  const borderColor = tone === 'error' ? 'var(--error-color)' : 'var(--success-color)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'fixed',
      bottom: '2rem',
      right: '2rem',
      background: 'var(--surface-card)',
      border: `1px solid ${borderColor}`,
      color: 'var(--text-primary)',
      padding: '1rem 1.8rem',
      borderRadius: 'var(--radius-md)',
      fontWeight: 500,
      backdropFilter: 'var(--blur-card)',
      boxShadow: 'var(--shadow-toast)',
      zIndex: 1000,
      display: 'flex',
      alignItems: 'center',
      gap: '0.5rem',
      animation: 'tp-toast-up 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)'
    }
  }, message, /*#__PURE__*/React.createElement("style", null, `@keyframes tp-toast-up { from { transform: translateY(30px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }`));
}

/**
 * Spinner — small rotating loader. Source: .spinner.
 */
function Spinner({
  size = 28
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      width: size,
      height: size,
      border: '3px solid rgba(139, 92, 246, 0.15)',
      borderRadius: '50%',
      borderTopColor: 'var(--primary-color)',
      animation: 'tp-spin 1s ease-in-out infinite',
      margin: '0 auto'
    }
  }, /*#__PURE__*/React.createElement("style", null, `@keyframes tp-spin { to { transform: rotate(360deg); } }`));
}
Object.assign(__ds_scope, { Toast, Spinner });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Input / Textarea — dark sunken field, violet focus ring.
 * Source: .input-group input / textarea.
 */
function Input({
  label,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '0.5rem'
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.85rem',
      color: 'var(--text-secondary)',
      fontWeight: 500
    }
  }, label), /*#__PURE__*/React.createElement("input", _extends({}, rest, {
    style: {
      background: 'var(--surface-sunken)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-md)',
      color: 'var(--text-primary)',
      padding: '0.8rem 1rem',
      fontFamily: 'var(--font-body)',
      fontSize: '0.95rem',
      transition: 'var(--transition-fast)',
      outline: 'none',
      ...style
    },
    onFocus: e => {
      e.currentTarget.style.borderColor = 'var(--primary-color)';
      e.currentTarget.style.boxShadow = 'var(--shadow-focus-ring)';
    },
    onBlur: e => {
      e.currentTarget.style.borderColor = 'var(--border-color)';
      e.currentTarget.style.boxShadow = 'none';
    }
  })));
}
function Textarea({
  label,
  rows = 4,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '0.5rem'
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.85rem',
      color: 'var(--text-secondary)',
      fontWeight: 500
    }
  }, label), /*#__PURE__*/React.createElement("textarea", _extends({
    rows: rows
  }, rest, {
    style: {
      background: 'var(--surface-sunken)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-md)',
      color: 'var(--text-primary)',
      padding: '1.2rem',
      fontFamily: 'var(--font-body)',
      fontSize: '1rem',
      lineHeight: 1.6,
      resize: 'none',
      outline: 'none',
      transition: 'var(--transition-fast)',
      ...style
    },
    onFocus: e => {
      e.currentTarget.style.borderColor = 'var(--primary-color)';
      e.currentTarget.style.boxShadow = 'var(--shadow-focus-ring)';
    },
    onBlur: e => {
      e.currentTarget.style.borderColor = 'var(--border-color)';
      e.currentTarget.style.boxShadow = 'none';
    }
  })));
}
Object.assign(__ds_scope, { Input, Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Select — styled dropdown matching the app's inline-styled <select> fields
 * (render engine, duration, schedule platform, posting hour).
 */
function Select({
  label,
  children,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: '0.35rem'
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.7rem',
      color: 'var(--text-secondary)'
    }
  }, label), /*#__PURE__*/React.createElement("select", _extends({}, rest, {
    style: {
      background: 'var(--surface-sunken-strong)',
      border: '1px solid var(--border-color)',
      color: 'var(--text-primary)',
      borderRadius: 'var(--radius-sm)',
      padding: '0.4rem 0.6rem',
      fontSize: '0.8rem',
      fontFamily: 'var(--font-body)',
      width: '100%',
      ...style
    }
  }), children));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
/**
 * Switch — pill toggle. Source: .switch-toggle / .slider-toggle
 * (24/7 Autopilot Automation toggle).
 */
function Switch({
  checked,
  onChange,
  label
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.6rem',
      cursor: 'pointer'
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '0.85rem',
      color: 'var(--text-primary)',
      fontWeight: 600
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'relative',
      display: 'inline-block',
      width: 42,
      height: 22
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    checked: checked,
    onChange: onChange,
    style: {
      opacity: 0,
      width: 0,
      height: 0,
      position: 'absolute'
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      inset: 0,
      background: checked ? 'var(--primary-color)' : 'rgba(255,255,255,0.15)',
      borderRadius: 34,
      transition: '.3s'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      height: 14,
      width: 14,
      left: checked ? 24 : 4,
      bottom: 4,
      background: 'white',
      borderRadius: '50%',
      transition: '.3s'
    }
  }))));
}

/**
 * Checkbox — plain accent-colored checkbox used in platform pickers
 * (Twitter/X, LinkedIn toggles).
 */
function Checkbox({
  checked,
  onChange,
  label
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.35rem',
      fontSize: '0.85rem',
      color: 'var(--text-primary)',
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    checked: checked,
    onChange: onChange,
    style: {
      width: '1.1rem',
      height: '1.1rem',
      accentColor: 'var(--primary-color)',
      cursor: 'pointer'
    }
  }), label);
}
Object.assign(__ds_scope, { Switch, Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
const {
  useState
} = React;
/**
 * Tabs — underline-active tab bar used everywhere (LinkedIn/Twitter/Instagram
 * post tabs, top main-nav, sub-nav). Source: .tab-btn/.c-tab-btn/.nav-link
 * all share this same pattern (color swap + gradient/solid underline).
 */
function Tabs({
  items,
  active,
  onChange,
  variant = 'default'
}) {
  const isNav = variant === 'nav';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: isNav ? '1.5rem' : '0.5rem',
      borderBottom: isNav ? 'none' : '1px solid var(--border-color)',
      paddingBottom: isNav ? 0 : '0.5rem'
    }
  }, items.map(item => {
    const isActive = item.value === active;
    return /*#__PURE__*/React.createElement("button", {
      key: item.value,
      onClick: () => onChange && onChange(item.value),
      style: {
        background: 'none',
        border: 'none',
        color: isActive ? 'var(--primary-color)' : 'var(--text-secondary)',
        padding: isNav ? '0.5rem 1rem' : '0.75rem 1.25rem',
        fontFamily: 'var(--font-display)',
        fontWeight: isNav ? 600 : 600,
        fontSize: isNav ? '1.1rem' : '1rem',
        cursor: 'pointer',
        position: 'relative',
        transition: 'var(--transition-fast)'
      }
    }, item.label, isActive && /*#__PURE__*/React.createElement("span", {
      style: {
        content: '""',
        position: 'absolute',
        bottom: isNav ? '-0.5rem' : '-0.6rem',
        left: isNav ? '1rem' : 0,
        right: isNav ? '1rem' : 'auto',
        width: isNav ? 'auto' : '100%',
        height: isNav ? 3 : 3,
        background: isNav ? 'var(--primary-grad)' : 'var(--primary-grad)',
        borderRadius: '1.5px'
      }
    }));
  }));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

__ds_ns.DropZone = __ds_scope.DropZone;

__ds_ns.TrendCard = __ds_scope.TrendCard;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Tag = __ds_scope.Tag;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.GlassCard = __ds_scope.GlassCard;

__ds_ns.ProgressStepper = __ds_scope.ProgressStepper;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.Spinner = __ds_scope.Spinner;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Textarea = __ds_scope.Textarea;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.Tabs = __ds_scope.Tabs;

})();
