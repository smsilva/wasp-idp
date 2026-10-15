<#-- platform: left column of the Split layout (#173). Title, text and terminal vary by page. -->
<#macro column pageId>
  <#assign device = (client?? && client.clientId == "platform-cli")>
  <#switch pageId>
    <#case "login-oauth2-device-verify-user-code"><#assign key = "device"><#break>
    <#case "login-oauth-grant"><#assign key = "grant"><#break>
    <#case "idp-review-user-profile"><#case "login-update-profile"><#assign key = "profile"><#break>
    <#case "error"><#case "login-page-expired"><#assign key = "error"><#break>
    <#case "info"><#assign key = "done"><#break>
    <#default><#assign key = device?then("deviceLogin", "login")>
  </#switch>
  <aside class="platform-ctx<#if key == "device"> keep-term</#if>">
    <h2>${msg("platform.ctx.${key}.title")} <em>${msg("platform.ctx.${key}.em")}</em></h2>
    <p>${msg("platform.ctx.${key}.text")}</p>
    <#if key == "login">
      <div class="platform-planes"><span>Developer Control</span><span>Integration &amp; Delivery</span><span>Resource</span><span>Observability</span><span>Security</span></div>
    </#if>
    <#if key != "profile" && key != "error">
      <div class="platform-term"><div class="tb"><i></i><i></i><i></i></div><pre><span class="p">$</span> ${msg("platform.ctx.${key}.cmd")}
<span class="cur"></span></pre></div>
    </#if>
    <#if device && (key == "device" || key == "deviceLogin" || key == "grant")>
      <ol class="platform-steps">
        <li class="<#if key == "device">now<#else>done</#if>">${msg("platform.step.code")}</li>
        <li class="<#if key == "deviceLogin">now<#elseif key == "grant">done</#if>">${msg("platform.step.google")}</li>
        <li class="<#if key == "grant">now</#if>">${msg("platform.step.authorize")}</li>
      </ol>
    </#if>
  </aside>
</#macro>

<#-- The platform-api symbol: the platform's layers between the braces of an API. -->
<#macro symbol>
  <svg viewBox="0 0 40 32" width="32" height="25" aria-hidden="true"><defs><linearGradient id="platform-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7cc4ff"/><stop offset="1" stop-color="#a48bff"/></linearGradient></defs><path d="M9 3c-3 0-4 1.5-4 4v4.5c0 2-1 3.5-3 4.5 2 1 3 2.5 3 4.5V25c0 2.5 1 4 4 4" fill="none" stroke="#a4abb8" stroke-width="2.4" stroke-linecap="round"/><path d="M31 3c3 0 4 1.5 4 4v4.5c0 2 1 3.5 3 4.5-2 1-3 2.5-3 4.5V25c0 2.5-1 4-4 4" fill="none" stroke="#a4abb8" stroke-width="2.4" stroke-linecap="round"/><path d="M20 7l9 5-9 5-9-5z" fill="url(#platform-g)"/><path d="M11 16.5l9 5 9-5" fill="none" stroke="url(#platform-g)" stroke-width="2.4" stroke-linejoin="round"/><path d="M11 21l9 5 9-5" fill="none" stroke="url(#platform-g)" stroke-width="2.4" stroke-linejoin="round" opacity=".6"/></svg>
</#macro>
