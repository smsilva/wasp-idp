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
    <div class="platform-brand"><span class="mark">w</span><span class="name">wasp <span>· platform</span></span></div>
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
