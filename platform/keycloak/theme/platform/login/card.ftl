<#-- platform: the pieces around the stock card (#537, variant D — Card + trail). Mockup: docs/idp/design/keycloak-theme/c-card.html. -->

<#-- The page's key: picks the sentence under the title, the badge and the device-flow step. -->
<#function key pageId>
  <#local device = (client?? && client.clientId == "platform-cli")>
  <#switch pageId>
    <#case "login"><#return device?then("deviceLogin", "login")>
    <#case "login-oauth2-device-verify-user-code"><#return "device">
    <#case "login-oauth-grant"><#return "grant">
    <#case "idp-review-user-profile"><#case "login-update-profile"><#return "profile">
    <#case "error"><#case "login-page-expired"><#return "error">
    <#case "info"><#return "done">
    <#default><#return "">
  </#switch>
</#function>

<#-- One sentence under the title. info.ftl ("done") already prints its own message below the title. -->
<#macro text key>
  <#if key?has_content && key != "done"><p class="platform-text">${msg("platform.card.${key}")}</p></#if>
</#macro>

<#macro badge key>
  <#if key == "error"><div class="platform-badge err" aria-hidden="true">✗</div>
  <#elseif key == "done" && !(message?? && message.type == "error")><div class="platform-badge ok" aria-hidden="true">✓</div></#if>
</#macro>

<#-- Device flow only: code → Google → authorize, as three dots under the card. The code page comes before
     Keycloak knows the client, so it always shows the trail. -->
<#macro steps key>
  <#if key == "device" || (client?? && client.clientId == "platform-cli")>
    <#local now = {"device": 0, "deviceLogin": 1, "grant": 2, "done": 3}[key]!-1>
    <#if now gte 0>
      <ol class="platform-steps">
        <#list ["code", "google", "authorize"] as step>
          <li class="<#if step?index lt now>done<#elseif step?index == now>now</#if>"<#if step?index == now> aria-current="step"</#if>>${msg("platform.step.${step}")}</li>
        </#list>
      </ol>
    </#if>
  </#if>
</#macro>

<#-- The platform-api symbol: the platform's layers between the braces of an API. -->
<#macro symbol>
  <svg viewBox="0 0 40 32" width="44" height="35" aria-hidden="true"><defs><linearGradient id="platform-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7cc4ff"/><stop offset="1" stop-color="#a48bff"/></linearGradient></defs><path d="M9 3c-3 0-4 1.5-4 4v4.5c0 2-1 3.5-3 4.5 2 1 3 2.5 3 4.5V25c0 2.5 1 4 4 4" fill="none" stroke="#a4abb8" stroke-width="2.4" stroke-linecap="round"/><path d="M31 3c3 0 4 1.5 4 4v4.5c0 2 1 3.5 3 4.5-2 1-3 2.5-3 4.5V25c0 2.5-1 4-4 4" fill="none" stroke="#a4abb8" stroke-width="2.4" stroke-linecap="round"/><path d="M20 7l9 5-9 5-9-5z" fill="url(#platform-g)"/><path d="M11 16.5l9 5 9-5" fill="none" stroke="url(#platform-g)" stroke-width="2.4" stroke-linejoin="round"/><path d="M11 21l9 5 9-5" fill="none" stroke="url(#platform-g)" stroke-width="2.4" stroke-linejoin="round" opacity=".6"/></svg>
</#macro>
