FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS base
WORKDIR /app
EXPOSE 80
EXPOSE 443

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ["src/Verge.HttpApi.Host/Verge.HttpApi.Host.csproj", "src/Verge.HttpApi.Host/"]
COPY ["src/Verge.HttpApi/Verge.HttpApi.csproj", "src/Verge.HttpApi/"]
COPY ["src/Verge.Application/Verge.Application.csproj", "src/Verge.Application/"]
COPY ["src/Verge.Application.Contracts/Verge.Application.Contracts.csproj", "src/Verge.Application.Contracts/"]
COPY ["src/Verge.EntityFrameworkCore/Verge.EntityFrameworkCore.csproj", "src/Verge.EntityFrameworkCore/"]
COPY ["src/Verge.Domain/Verge.Domain.csproj", "src/Verge.Domain/"]
COPY ["src/Verge.Domain.Shared/Verge.Domain.Shared.csproj", "src/Verge.Domain.Shared/"]

RUN dotnet restore "src/Verge.HttpApi.Host/Verge.HttpApi.Host.csproj"
COPY . .
WORKDIR "/src/src/Verge.HttpApi.Host"
RUN dotnet build "Verge.HttpApi.Host.csproj" -c Release -o /app/build

FROM build AS publish
RUN dotnet publish "Verge.HttpApi.Host.csproj" -c Release -o /app/publish

FROM base AS final
WORKDIR /app
COPY --from=publish /app/publish .
ENTRYPOINT ["dotnet", "Verge.HttpApi.Host.dll"]
